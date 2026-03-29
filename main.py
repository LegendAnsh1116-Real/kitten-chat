from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uuid, random, bcrypt
import sqlite3

# Connect DB (auto creates file)
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# =========================
# DB TABLES
# =========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    public_id TEXT,
    password TEXT,
    parentName TEXT,
    childName TEXT,
    gender TEXT,
    profileImg TEXT,
    pair_id TEXT)

""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS pairs (
    code TEXT PRIMARY KEY,
    pair_id TEXT
)
""")

conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair_id TEXT,
    sender_id TEXT,
    message TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

app = FastAPI()
import asyncio

# =========================
# STATIC + FRONTEND
# =========================

app.mount("/assets", StaticFiles(directory="kitten-ui/assets"), name="assets")

@app.get("/")
def serve():
    return FileResponse("kitten-ui/index.html")

# CORS (for safety)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# STORAGE (temporary memory)
# =========================

rooms = {}        # pairing rooms
# REMOVE in-memory users (we use SQLite now)

CHARS = "ABCDEFGHJKLNPQRSTUVXYZ123456789"


# =========================
# UTIL FUNCTIONS
# =========================

def generate_code():
    while True:
        code = "".join(random.choice(CHARS) for _ in range(5))

        cursor.execute("SELECT public_id FROM users WHERE public_id=?", (code,))
        exists = cursor.fetchone()

        if code not in rooms and not exists:
            return code


def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())


def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed)


# =========================
# WEBSOCKET
# =========================

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    user_id = str(uuid.uuid4())
    current_code = None

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            # =========================
            # CHECK CODE (ANTI-COLLISION)
            # =========================
            if msg_type == "check_code":
                code = data["code"]

                cursor.execute("SELECT public_id FROM users WHERE public_id=?", (code,))
                exists = cursor.fetchone()

                if exists or code in rooms:
                    await ws.send_json({
                        "type": "code_invalid"
                    })
                else:
                    await ws.send_json({
                        "type": "code_valid"
                    })

            # =========================
            # CREATE CODE
            # =========================
            elif msg_type == "create_code":
                code = data["code"]   # 🔥 MOVE THIS FIRST

                if code not in rooms:
                    cursor.execute("INSERT INTO pairs (code) VALUES (?)", (code,))
                    conn.commit()

                    rooms[code] = {
                        "users": {},
                        "profiles": {},
                        "pair_id": None,
                        "confirmed": set()
                    }

                    await ws.send_json({
                        "type": "connected",
                        "user_id": user_id
                    })

                if user_id not in rooms[code]["users"]:
                    rooms[code]["users"][user_id] = ws
                current_code = code

            # =========================
            # JOIN CODE
            # =========================
            elif msg_type == "join_code":
                code = data["code"]

                if current_code == code:
                    await ws.send_json({
                        "type": "error",
                        "message": "You cannot enter your own code"
                    })
                    continue

                if code not in rooms:
                    await ws.send_json({
                        "type": "error",
                        "message": "Invalid or expired code"
                    })
                    continue

                if len(rooms[code]["users"]) >= 2:
                    await ws.send_json({
                        "type": "error",
                        "message": "Room full"
                    })
                    continue

                if user_id not in rooms[code]["users"]:
                   rooms[code]["users"][user_id] = ws
                current_code = code

                # notify both users
                for u in rooms[code]["users"].values():
                    await u.send_json({"type": "paired"})

            # =========================
            # PROFILE READY
            # =========================
            elif msg_type == "profile_ready":
                if not current_code:
                    continue

                room = rooms[current_code]

                # ensure only 2 users max
                if user_id not in room["profiles"] and len(room["profiles"]) < 2:
                    room["profiles"][user_id] = {
                        "parentName": data.get("parentName", ""),
                        "childName": data.get("childName", ""),
                        "gender": data.get("gender", ""),
                        "profileImg": data.get("profileImg", "")
                    }

                # when both ready
                if len(room["profiles"]) == 2:

                    # create pair_id once
                    if not room["pair_id"]:
                        room["pair_id"] = str(uuid.uuid4())

                    # save to DB
                    cursor.execute("UPDATE pairs SET pair_id=? WHERE code=?", (room["pair_id"], current_code))
                    conn.commit()

                    for u in room["users"].values():
                        await u.send_json({
                            "type": "both_profiles_ready"
                        })

            elif msg_type == "confirm_profiles":
                if not current_code:
                    continue

                room = rooms[current_code]

                # ensure set exists
                if "confirmed" not in room:
                    room["confirmed"] = set()

                room["confirmed"].add(user_id)

                # 🔥 SAFETY: ensure only valid users counted
                room["confirmed"] = {
                    uid for uid in room["confirmed"]
                    if uid in room["users"]
                }

                # ✅ FINAL CHECK
                if len(room["confirmed"]) >= 2 and len(room["users"]) == 2:

                    for u in room["users"].values():
                        await u.send_json({
                            "type": "start_chat"
                        })

                    # 🔥 OPTIONAL RESET (prevents future bugs)
                    room["confirmed"].clear()

            # =========================
            # CREATE ACCOUNT (ID + PASSWORD)
            # =========================
            elif msg_type == "create_account":
                public_id = data["public_id"]
                password = data["password"]

                # check DB uniqueness
                cursor.execute("SELECT public_id FROM users WHERE public_id=?", (public_id,))
                if cursor.fetchone():
                    await ws.send_json({
                        "type": "error",
                        "message": "ID already taken"
                    })
                    continue

                profile = rooms[current_code]["profiles"].get(user_id)

                if not profile:
                    await ws.send_json({
                        "type": "error",
                        "message": "Profile not found"
                    })
                    continue

                hashed = hash_password(password)

                cursor.execute("""
                INSERT INTO users (id, public_id, password, parentName, childName, gender, profileImg, pair_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    public_id,
                    hashed,
                    profile["parentName"],
                    profile["childName"],
                    profile["gender"],
                    profile["profileImg"],
                    rooms[current_code]["pair_id"]
                ))

                conn.commit()

                await ws.send_json({
                    "type": "account_created",
                    "public_id": public_id
                })

            # =========================
            # LOGIN
            # =========================
            elif msg_type == "login":
                public_id = data["public_id"]
                password = data["password"]

                cursor.execute("""
                SELECT id, password, parentName, childName, gender, profileImg, pair_id
                FROM users WHERE public_id=?
                """, (public_id,))

                user = cursor.fetchone()

                if not user:
                    await ws.send_json({
                        "type": "error",
                        "message": "User not found"
                    })
                    continue

                uid, hashed_pw, parentName, childName, gender, profileImg, pair_id = user

                if not verify_password(password, hashed_pw):
                    await ws.send_json({
                        "type": "error",
                        "message": "Wrong password"
                    })
                    continue

                await ws.send_json({
                    "type": "login_success",
                    "profile": {
                        "parentName": parentName,
                        "childName": childName,
                        "gender": gender,
                        "profileImg": profileImg
                    },
                    "pair_id": pair_id
                })

            elif msg_type == "send_message":
                message = data["message"]

                room = rooms.get(current_code)
                if not room or not room["pair_id"]:
                    continue

                pair_id = room["pair_id"]

                # save message
                cursor.execute("""
                INSERT INTO messages (pair_id, sender_id, message)
                VALUES (?, ?, ?)
                """, (pair_id, user_id, message))
                conn.commit()

                # send message (NO seen yet)
                for uid, u in room["users"].items():
                    await u.send_json({
                        "type": "new_message",
                        "message": message,
                        "sender": user_id
                    })
           
            elif msg_type == "seen":
                if not current_code:
                     continue

                room = rooms.get(current_code)
                if not room:
                    continue
             
                # notify OTHER user only
                for uid, u in room["users"].items():
                    if uid != user_id:
                        await u.send_json({
                            "type": "seen"
                        })

    except WebSocketDisconnect:
        if current_code and current_code in rooms:
            rooms[current_code].get("confirmed", set()).discard(user_id)
            rooms[current_code]["users"].pop(user_id, None)
            rooms[current_code]["profiles"].pop(user_id, None)
            
            # 🔥 DELETE ROOM IF EMPTY
            if not rooms[current_code]["users"]:
                rooms.pop(current_code)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)