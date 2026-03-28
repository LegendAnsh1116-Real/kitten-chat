import json
import os

MEMORY_FILE = "memory.json"

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {}
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)

def update_memory_from_message(message, emotion):
    memory = load_memory()

    memory["bond_points"] = memory.get("bond_points", 0) + 1
    memory["last_event"] = message
    memory["mood"] = emotion

    if "love" in message.lower():
        fav = memory.get("favorite_words", [])
        if "love" not in fav:
            fav.append("love")
        memory["favorite_words"] = fav

    save_memory(memory)

def save_last_reply(text):
    memory = load_memory()
    memory["last_reply"] = text
    save_memory(memory)

def check_and_update_growth():
    memory = load_memory()

    age = memory.get("age_days", 1)
    bond = memory.get("bond_points", 0)
    milestones = memory.get("milestones", [])

    # Age-based growth
    if age >= 3 and "toddler" not in milestones:
        milestones.append("toddler")

    if age >= 7 and "playful_child" not in milestones:
        milestones.append("playful_child")

    if age >= 14 and "attached_child" not in milestones:
        milestones.append("attached_child")

    # Bond-based growth
    if bond >= 10 and "trusting" not in milestones:
        milestones.append("trusting")

    if bond >= 20 and "deeply_attached" not in milestones:
        milestones.append("deeply_attached")

    memory["milestones"] = milestones
    save_memory(memory)
