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
                conn.commit()
            
                # prevent overwrite
                if code not in rooms:
                    rooms[code] = {
                        "users": {},
                        "profiles": {},
                        "pair_id": None
                    }
                    await ws.send_json({
                        "type": "connected",
                        "user_id": user_id
                    })

                rooms[code]["users"][user_id] = ws
                current_code = code

            # =========================
            # JOIN CODE
            # =========================
            elif msg_type == "join_code":
                code = data["code"]

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

                    user_ids_list = list(room["profiles"].keys())

                    u1, u2 = user_ids_list[0], user_ids_list[1]

                    # send partner data
                    await room["users"][u1].send_json({
                        "type": "partner_ready",
                        **room["profiles"][u2]
                    })

                    await room["users"][u2].send_json({
                        "type": "partner_ready",
                        **room["profiles"][u1]
                    })

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

                # send to both users
                for u in room["users"].values():
                    await u.send_json({
                        "type": "new_message",
                        "message": message,
                        "sender": user_id
                    })

    except WebSocketDisconnect:
        if current_code and current_code in rooms:
            rooms[current_code]["users"].pop(user_id, None)
            rooms[current_code]["profiles"].pop(user_id, None)

            # 🔥 DELETE ROOM IF EMPTY
            if not rooms[current_code]["users"]:
                rooms.pop(current_code)
