import uuid
import uvicorn

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.mount("/assets", StaticFiles(directory="assets"), name="assets")

@app.get("/")
async def serve():
    return FileResponse("index.html")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# pairing_code -> {"owner": socket_id, "ws": WebSocket}
pairs: dict[str, dict] = {}

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    socket_id = str(uuid.uuid4())
    current_code = None

    try:
        while True:
            data = await ws.receive_json()
            action = data.get("type")

            # =========================
            # CREATE PAIRING CODE
            # =========================
            if action == "create_code":
                code = data.get("code")

                # remove previous code if exists
                if current_code and current_code in pairs:
                    del pairs[current_code]

                pairs[code] = {
                    "owner": socket_id,
                    "ws": ws
                }

                current_code = code
                print("Code created:", code)

            # =========================
            # JOIN PAIRING CODE
            # =========================
            elif action == "join_code":
                code = data.get("code")

                # invalid / expired
                if code not in pairs:
                    await ws.send_json({
                        "type": "error",
                        "message": "Invalid or expired code"
                    })
                    continue  # ✅ keep socket alive

                owner_data = pairs[code]

                # 🚫 block self-connection
                if owner_data["owner"] == socket_id:
                    await ws.send_json({
                        "type": "error",
                        "message": "You can’t connect to your own code"
                    })
                    continue  # ✅ keep socket alive

                partner_ws = owner_data["ws"]
                pairs.pop(code)

                # notify both users
                await ws.send_json({"type": "paired"})
                await partner_ws.send_json({"type": "paired"})

                print("Paired with code:", code)

    except WebSocketDisconnect:
        if current_code and current_code in pairs:
            del pairs[current_code]
        print("Client disconnected")


import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
