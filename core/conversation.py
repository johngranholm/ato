"""
Persistent conversation thread - the backbone of continuity.
This is what makes A.T.O. remember what she just did, across turns AND reboots.
The system prompt is NOT stored here; it's prepended fresh each run.
"""
import os
import time
import json
import threading

from ato import config

CONV_FILE = os.path.join(config.STATE_DIR, "conversation.json")
MAX_MESSAGES = 80          # rolling cap to control token growth
MAX_TOOL_CHARS = 4000      # truncate stored tool output

_lock = threading.Lock()
CONV = {"messages": [], "updated": 0}


def load():
    global CONV
    try:
        with open(CONV_FILE, "r", encoding="utf-8") as f:
            CONV = json.load(f)
    except Exception:
        CONV = {"messages": [], "updated": 0}


def save():
    with _lock:
        try:
            tmp = CONV_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                json.dump(CONV, f, indent=2)
            os.replace(tmp, CONV_FILE)
        except Exception:
            pass


def append(msg):
    # truncate bulky tool outputs before persisting
    if msg.get("role") == "tool" and isinstance(msg.get("content"), str):
        if len(msg["content"]) > MAX_TOOL_CHARS:
            msg = dict(msg)
            msg["content"] = msg["content"][:MAX_TOOL_CHARS] + "\n...(truncated)"
    CONV["messages"].append(msg)
    CONV["updated"] = time.time()
    _trim()
    save()


def messages():
    return list(CONV["messages"])


def _trim():
    msgs = CONV["messages"]
    if len(msgs) <= MAX_MESSAGES:
        return
    # cut on a 'user' boundary so we never orphan a tool response
    cut = len(msgs) - MAX_MESSAGES
    while cut < len(msgs) and msgs[cut].get("role") != "user":
        cut += 1
    if cut >= len(msgs):
        cut = len(msgs) - MAX_MESSAGES
    CONV["messages"] = msgs[cut:]


def clear():
    CONV["messages"] = []
    CONV["updated"] = time.time()
    save()


def last_user_text():
    for m in reversed(CONV["messages"]):
        if m.get("role") == "user":
            return m.get("content", "")
    return None


def recent_for_ui(n=40):
    """Lightweight view to repopulate the terminal on reload."""
    out = []
    for m in CONV["messages"][-n:]:
        role = m.get("role")
        if role == "user":
            out.append({"who": "you", "text": m.get("content", "")})
        elif role == "assistant" and m.get("content"):
            out.append({"who": "ato", "text": m.get("content", "")})
    return out