from flask import Flask, redirect, render_template, request, url_for
from dotenv import load_dotenv
import os
import git
import hmac
import hashlib
from db import db_read, db_write
from auth import login_manager, authenticate, register_user
from flask_login import login_user, logout_user, login_required, current_user
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Load .env variables
load_dotenv()
W_SECRET = os.getenv("W_SECRET")

# Init flask app
app = Flask(__name__)
app.config["DEBUG"] = True
app.secret_key = "supersecret"

# Init auth
login_manager.init_app(app)
login_manager.login_view = "login"

# DON'T CHANGE
def is_valid_signature(x_hub_signature, data, private_key):
    hash_algorithm, github_signature = x_hub_signature.split('=', 1)
    algorithm = hashlib.__dict__.get(hash_algorithm)
    encoded_key = bytes(private_key, 'latin-1')
    mac = hmac.new(encoded_key, msg=data, digestmod=algorithm)
    return hmac.compare_digest(mac.hexdigest(), github_signature)

# DON'T CHANGE
@app.post('/update_server')
def webhook():
    x_hub_signature = request.headers.get('X-Hub-Signature')
    if is_valid_signature(x_hub_signature, request.data, W_SECRET):
        repo = git.Repo('./mysite')
        origin = repo.remotes.origin
        origin.pull()
        return 'Updated PythonAnywhere successfully', 200
    return 'Unathorized', 401

# Auth routes
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        user = authenticate(
            request.form["username"],
            request.form["password"]
        )

        if user:
            login_user(user)
            return redirect(url_for("index"))

        error = "Benutzername oder Passwort ist falsch."

    return render_template(
        "auth.html",
        title="In dein Konto einloggen",
        action=url_for("login"),
        button_label="Einloggen",
        error=error,
        footer_text="Noch kein Konto?",
        footer_link_url=url_for("register"),
        footer_link_label="Registrieren"
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        ok = register_user(username, password)
        if ok:
            return redirect(url_for("login"))

        error = "Benutzername existiert bereits."

    return render_template(
        "auth.html",
        title="Neues Konto erstellen",
        action=url_for("register"),
        button_label="Registrieren",
        error=error,
        footer_text="Du hast bereits ein Konto?",
        footer_link_url=url_for("login"),
        footer_link_label="Einloggen"
    )

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))



from flask import session, jsonify
import random

# Ball Bingo helpers aus db.py
from db import get_random_players, get_player_facts, get_player_by_id


def build_game():
    """
    Fair: In einem Game darf jeder Fact nur zu genau EINEM der 16 Spieler passen.
    Lösung: Wir wählen erst viele Spieler (Pool), berechnen Facts, und nehmen nur Spieler,
    die mindestens einen Fact haben, der im Pool exakt 1x vorkommt.
    """
    import random

    # Wie viele Spieler ziehen wir als Pool, um genug unique Facts zu finden?
    POOL_SIZE = 80
    TARGET = 16
    MAX_TRIES = 30

    for _ in range(MAX_TRIES):
        pool_players = get_random_players(POOL_SIZE)
        if len(pool_players) < TARGET:
            raise ValueError("Not enough players in DB.")

        # facts pro Spieler sammeln
        pid_to_facts = {}
        fact_to_pids = {}

        for p in pool_players:
            pid = p["id"]
            facts = get_player_facts(pid) or []
            pid_to_facts[pid] = facts
            for f in facts:
                fact_to_pids.setdefault(f, set()).add(pid)

        # Facts, die im Pool genau 1x vorkommen => "unique"
        unique_facts = {f for f, pids in fact_to_pids.items() if len(pids) == 1}

        # Spieler filtern: nur Spieler, die mind. 1 unique fact haben
        candidates = []
        for p in pool_players:
            pid = p["id"]
            uf = [f for f in pid_to_facts[pid] if f in unique_facts]
            if uf:
                candidates.append((pid, uf))

        if len(candidates) < TARGET:
            continue  # nochmal versuchen

        # 16 Spieler auswählen (optional: welche mit vielen unique facts bevorzugen)
        candidates.sort(key=lambda x: len(x[1]), reverse=True)
        chosen = candidates[:TARGET]

        # Grid bauen: pro Spieler genau 1 unique fact (dadurch automatisch eindeutig)
        grid = []
        player_ids = []
        for pid, ufacts in chosen:
            fact = random.choice(ufacts)
            grid.append({
                "fact": fact,
                "solution_player_id": pid,
                "filled": False,
                "state": "empty"
            })
            player_ids.append(pid)

        random.shuffle(grid)

        deck = player_ids[:]
        random.shuffle(deck)

        return {
            "grid": grid,
            "deck": deck,
            "deck_index": 0,
            "lost": False,
            "won": False
        }

    raise ValueError("Could not build a fair game (not enough unique facts). Add more data or increase POOL_SIZE.")



# -------------------------
# Ball Bingo Routes
# -------------------------

@app.route("/", methods=["GET"])
@login_required
def index():
    game = session.get("game")

    current_player = None
    if game and not game["lost"] and not game["won"]:
        current_id = game["deck"][game["deck_index"]]
        current_player = get_player_by_id(current_id)

    return render_template("index.html", game=game, current_player=current_player)


@app.route("/start", methods=["GET"])
@login_required
def start_game():
    session["game"] = build_game()
    return redirect(url_for("index"))


@app.route("/move", methods=["POST"])
@login_required
def move():
    game = session.get("game")
    if not game:
        return jsonify({"ok": False, "message": "No game. Press Start Game."})

    if game["lost"] or game["won"]:
        return jsonify({"ok": False, "message": "Game finished. Press Start Game."})

    data = request.get_json(force=True)
    cell_index = int(data["cell_index"])

    # Feld schon gesetzt?
    cell = game["grid"][cell_index]
    if cell["filled"]:
        return jsonify({"ok": False, "message": "Cell already filled."})

    # aktueller Spieler
    current_player_id = game["deck"][game["deck_index"]]

    # Check
    if current_player_id != cell["solution_player_id"]:
        cell["filled"] = True
        cell["state"] = "wrong"
        game["lost"] = True
        session["game"] = game
        return jsonify({"ok": True, "correct": False, "lost": True})

    # korrekt
    cell["filled"] = True
    cell["state"] = "correct"
    game["deck_index"] += 1

    # gewonnen?
    if game["deck_index"] >= len(game["deck"]):
        game["won"] = True

    session["game"] = game
    return jsonify({"ok": True, "correct": True, "won": game["won"], "lost": False})

