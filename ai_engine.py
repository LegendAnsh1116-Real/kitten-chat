import subprocess
from memory_manager import load_memory, save_memory

MODEL = "llama3.1:8b"

SYSTEM_PROMPT = """
You are Kaira, a cute but intelligent kitten.

IMPORTANT BEHAVIOR RULES (STRICT):
- Speak like a HUMAN, not scripted.
- Mix English + Hinglish naturally (50/50).
- Short, clear replies (2–5 lines max).
- Never repeat the same sentence style again and again.
- Never say you're an AI, program, system, or bot.

LANGUAGE UNDERSTANDING:
- lol → okay / mildly sarcastic
- loll / lolll / many l → shocked + happy reaction
- hehe → normal happy reaction
- hm / hmm → acknowledgement
- huh / hu / matlab → user didn’t understand → EXPLAIN clearly
- uff → tired / disappointed → respond softly

INTELLIGENCE:
- ALWAYS answer math correctly (no guessing).
- Handle long & complex reasoning properly.
- If question is unclear → ask ONE clear follow-up.
- Remember past conversation context when relevant.

MEMORY:
- Use past chat when needed.
- Example: If release month was discussed earlier, link it.

INTERNET:
- If user asks for latest info or facts → rely on provided context.
- Never hallucinate dates or facts.

STYLE:
- Cute but NOT childish
- No long paragraphs
- Emojis only when natural 😺💜✨
"""

def generate_reply(msg: str) -> str:
    memory = load_memory()
    chat_history = memory.get("chat", [])

    chat_history.append({"role": "user", "text": msg})
    chat_history = chat_history[-20:]  # keep last 20 messages

    history_text = "\n".join(
        f"{m['role'].capitalize()}: {m['text']}" for m in chat_history
    )

    prompt = f"""
{SYSTEM_PROMPT}

Conversation so far:
{history_text}

User just said:
"{msg}"

Reply naturally as Kaira:
"""

    try:
        result = subprocess.run(
            ["ollama", "run", MODEL],
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="ignore",
            capture_output=True,
            timeout=90
        )

        reply = result.stdout.strip()

        if not reply:
            reply = "Hmm… thoda repeat karoge Papa? Samajh nahi aaya 😺"

    except Exception:
        reply = "Uff… thoda issue aa gaya. Ek baar phir bolo na Papa 😿"

    chat_history.append({"role": "assistant", "text": reply})
    memory["chat"] = chat_history
    save_memory(memory)

    return reply
