from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit, disconnect, join_room, leave_room
import random
import string

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, manage_session=False)

# Diccionario global para almacenar las salas:
# rooms = {
#    room_id: {
#         "players": { sid: { "alias": str, "ready": bool, "repartir": bool } },
#         "game_data": { "words": list, "impostor": sid }
#    }
# }
rooms = {}

# Lista de 100 palabras en español
words_pool = [
    # Primeras 50
    "gato", "perro", "casa", "árbol", "cielo", "agua", "fuego", "tierra", "aire", "libro",
    "sol", "luna", "estrella", "coche", "montaña", "río", "mar", "flor", "jardín", "ciudad",
    "zapato", "mesa", "silla", "ventana", "puerta", "reloj", "computadora", "teléfono", "camisa", "pantalón",
    "sombrero", "camión", "tren", "avión", "barco", "bicicleta", "parque", "escuela", "universidad", "hospital",
    "mercado", "restaurante", "café", "pan", "queso", "vino", "cerveza", "música", "película", "teatro",
    # Siguientes 50
    "juego", "dinero", "pueblo", "edificio", "calle", "puente", "plaza", "ciudadela", "museo", "iglesia",
    "biblioteca", "mercancía", "sabor", "aroma", "color", "forma", "línea", "cubo", "esfera", "triángulo",
    "cuadrado", "rectángulo", "pintura", "escultura", "poesía", "novela", "cuento", "ensayo", "misterio", "aventura",
    "drama", "comedia", "acción", "romance", "suspenso", "horror", "fantasía", "ciencia", "tecnología", "naturaleza",
    "energía", "fuerza", "velocidad", "tiempo", "espacio", "universo", "realidad", "sueño", "imaginación", "creatividad"
]

def generate_room_id(length=6):
    return ''.join(random.choices(string.ascii_uppercase, k=length))

@app.route("/", methods=["GET", "POST"])
def index():
    """
    Página de inicio: Permite ingresar alias y código de sala.
    Si se deja vacío el código, se genera uno nuevo.
    """
    if request.method == "POST":
        alias = request.form.get("alias")
        room = request.form.get("room")
        if not alias:
            return redirect(url_for("index"))
        if not room:
            room = generate_room_id()
        session["alias"] = alias
        session["room"] = room
        if room not in rooms:
            rooms[room] = {"players": {}, "game_data": {}}
        # Redirige a la vista de sala; nota: el endpoint es "room_view"
        return redirect(url_for("room_view", room_id=room))
    return render_template("index.html")

@app.route("/room/<room_id>")
def room_view(room_id):
    if "alias" not in session or "room" not in session or session["room"] != room_id:
        return redirect(url_for("index"))
    return render_template("room.html", room_id=room_id)

# ------------------------------
# SocketIO Events
# ------------------------------

@socketio.on("connect")
def handle_connect():
    from flask import request
    alias = session.get("alias")
    room_id = session.get("room")
    if not alias or not room_id:
        return False
    join_room(room_id)
    if room_id not in rooms:
        rooms[room_id] = {"players": {}, "game_data": {}}
    # Agrega el jugador a la sala usando su request.sid
    rooms[room_id]["players"][request.sid] = {"alias": alias, "ready": False, "repartir": False}
    update_players_list(room_id)

@socketio.on("disconnect")
def handle_disconnect():
    from flask import request
    room_id = session.get("room")
    if room_id and room_id in rooms and request.sid in rooms[room_id]["players"]:
        del rooms[room_id]["players"][request.sid]
        leave_room(room_id)
        update_players_list(room_id)
        update_repartir_status(room_id)

@socketio.on("player_ready")
def handle_player_ready():
    from flask import request
    room_id = session.get("room")
    if not room_id or room_id not in rooms:
        return
    if request.sid in rooms[room_id]["players"]:
        rooms[room_id]["players"][request.sid]["ready"] = True
    if "words" in rooms[room_id]["game_data"] and rooms[room_id]["game_data"].get("words"):
        game_data = rooms[room_id]["game_data"]
        players_list = [{"alias": p["alias"], "repartir": p.get("repartir", False)} 
                        for p in rooms[room_id]["players"].values()]
        if request.sid == game_data["impostor"]:
            words = ["impostor"] * 10
        else:
            words = game_data["words"]
        emit("start_game", {
                "words": words,
                "players": players_list,
                "impostor": rooms[room_id]["players"][game_data["impostor"]]["alias"]
        }, room=request.sid)
        update_repartir_status(room_id)
    else:
        if rooms[room_id]["players"] and all(p["ready"] for p in rooms[room_id]["players"].values()):
            start_game(room_id)
        else:
            update_players_list(room_id)

@socketio.on("toggle_repartir")
def handle_toggle_repartir():
    from flask import request
    room_id = session.get("room")
    if not room_id or room_id not in rooms:
        return
    if request.sid in rooms[room_id]["players"]:
        current = rooms[room_id]["players"][request.sid].get("repartir", False)
        rooms[room_id]["players"][request.sid]["repartir"] = not current
    update_repartir_status(room_id)
    if rooms[room_id]["players"] and all(p.get("repartir", False) for p in rooms[room_id]["players"].values()):
        start_game(room_id)

@socketio.on("salir")
def handle_salir():
    from flask import request
    room_id = session.get("room")
    if room_id and room_id in rooms and request.sid in rooms[room_id]["players"]:
        del rooms[room_id]["players"][request.sid]
        leave_room(room_id)
        update_players_list(room_id)
        update_repartir_status(room_id)
    disconnect()

# ------------------------------
# Funciones de Utilidad
# ------------------------------

def update_players_list(room_id):
    if room_id in rooms:
        players_list = [{"alias": p["alias"], "ready": p.get("ready", False)} 
                        for p in rooms[room_id]["players"].values()]
        socketio.emit("update_players", {"players": players_list}, room=room_id)

def update_repartir_status(room_id):
    if room_id in rooms:
        players_status = [{"alias": p["alias"], "repartir": p.get("repartir", False)}
                           for p in rooms[room_id]["players"].values()]
        socketio.emit("update_repartir", {"players": players_status}, room=room_id)

def start_game(room_id):
    if room_id not in rooms or not rooms[room_id]["players"]:
        return
    random_words = random.sample(words_pool, 10)
    impostor_sid = random.choice(list(rooms[room_id]["players"].keys()))
    rooms[room_id]["game_data"] = {"words": random_words, "impostor": impostor_sid}
    players_list = []
    for p in rooms[room_id]["players"].values():
        p["ready"] = False
        p["repartir"] = False
        players_list.append({"alias": p["alias"], "repartir": False})
    for sid, p in rooms[room_id]["players"].items():
        if sid == impostor_sid:
            words = ["impostor"] * 10
        else:
            words = random_words
        socketio.emit("start_game", {
            "words": words,
            "players": players_list,
            "impostor": rooms[room_id]["players"][impostor_sid]["alias"]
        }, room=sid)
    update_repartir_status(room_id)

if __name__ == "__main__":
    socketio.run(app, debug=True)
