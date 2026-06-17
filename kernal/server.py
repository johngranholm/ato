"""
HTTP boundary. KERNEL FILE - never self-edited.
Lane 1 hardening: per-boot session token + Origin/Host allowlist so no other
browser tab can drive the shell. Serves the UI and routes events.
"""
import os
import json
import queue
import secrets
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from ato import config
from ato.core import bus as busmod
from ato.core import memory as mem
from ato.core import execution as ex
from ato.core import selfedit
from ato.core import sandbox

SESSION_TOKEN = secrets.token_urlsafe(24)        # fresh per worker
ALLOWED_HOSTS = {f"127.0.0.1:{config.PORT}", f"localhost:{config.PORT}"}
ALLOWED_ORIGINS = {f"http://127.0.0.1:{config.PORT}", f"http://localhost:{config.PORT}"}

# functions injected by runtime.main() to avoid import cycles
HOOKS = {"greet": None, "agent_run": None, "tts": None, "list_glbs": None,
         "read_glb": None, "info_extra": None}

_greeted = {"done": False}


def _load_ui():
    try:
        with open(config.UI_HTML, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "<h1>ui.html missing</h1>"


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def make_server():
    import time
    last = None
    for _ in range(40):
        try:
            return Server(("127.0.0.1", config.PORT), Handler)
        except OSError as e:
            last = e; time.sleep(0.2)
    raise last


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    # ---- guards ----
    def _origin_ok(self):
        if self.headers.get("Host", "") not in ALLOWED_HOSTS:
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            return False
        return True

    def _authed(self):
        return self.headers.get("X-ATO-Token") == SESSION_TOKEN

    # ---- io ----
    def _send(self, code, ctype, body):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, "application/json", json.dumps(obj).encode())

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    # ---- GET ----
    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            page = _load_ui().replace("__SESSION_TOKEN__", SESSION_TOKEN)
            self._send(200, "text/html; charset=utf-8", page.encode())
        elif p == "/ping":
            self._json({"boot": config.BOOT_ID})
        elif p == "/info":
            extra = HOOKS["info_extra"]() if HOOKS["info_extra"] else {}
            self._json({"model": config.MODEL, "mode": busmod.state["mode"],
                        "os": config.OSNAME, "memory_on": mem.MEM.get("memory_on", True),
                        "tts": bool(config.TTS_ENABLED),
                        "sandbox": sandbox.status(), **extra})
        elif p == "/backups":
            self._json(selfedit.list_versions())
        elif p == "/glbs":
            self._json({"glbs": HOOKS["list_glbs"]() if HOOKS["list_glbs"] else [],
                        "dir": config.GLB_DIR})
        elif p == "/glb":
            f = (parse_qs(urlparse(self.path).query).get("f") or [""])[0]
            data = HOOKS["read_glb"](f) if HOOKS["read_glb"] else None
            if data is None:
                self._send(404, "text/plain", b"no glb")
            else:
                self._send(200, "model/gltf-binary", data)
        elif p == "/hello":
            if not _greeted["done"] and HOOKS["greet"]:
                _greeted["done"] = True
                threading.Thread(target=HOOKS["greet"], daemon=True).start()
            self._json({"ok": True})
        elif p == "/stream":
            if not self._origin_ok():
                self._send(403, "text/plain", b"bad origin"); return
            t = (parse_qs(urlparse(self.path).query).get("t") or [""])[0]
            if t != SESSION_TOKEN:
                self._send(401, "text/plain", b"unauthorized"); return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive"); self.end_headers()
            q = busmod.bus.subscribe()
            try:
                while True:
                    try:
                        ev = q.get(timeout=15)
                        self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                busmod.bus.unsubscribe(q)
        else:
            self._send(404, "text/plain", b"not found")

    # ---- POST ----
    def do_POST(self):
        if not self._origin_ok():
            self._json({"error": "bad origin/host"}, 403); return
        if not self._authed():
            self._json({"error": "unauthorized"}, 401); return
        b = self._body()
        p = urlparse(self.path).path

        if p == "/goal":
            goal = (b.get("goal") or "").strip()
            with busmod.goal_lock:
                if goal and not busmod.state["running"]:
                    busmod.state["running"] = True
                    threading.Thread(target=HOOKS["agent_run"], args=(goal,),
                                     daemon=True).start()
            self._json({"ok": True})
        elif p == "/approve":
            busmod.approval["text"] = b.get("text", ""); busmod.approval_event.set()
            self._json({"ok": True})
        elif p == "/cancel":
            busmod.state["cancel"] = True; busmod.approval_event.set(); ex.kill_current()
            busmod.bus.emit("system", "Stop requested."); self._json({"ok": True})
        elif p == "/reset":
            busmod.do_reset("manual reset button"); self._json({"ok": True})
        elif p == "/rollback":
            to = (b.get("to") or "").strip() or None
            ok, msg = selfedit.rollback(to)
            if ok:
                busmod.bus.emit("system", "Rollback: " + msg)
                busmod.schedule_reboot("rollback")
            else:
                busmod.bus.emit("error", "Rollback failed: " + msg, mood="frustrated")
            self._json({"ok": ok, "msg": msg})
        elif p == "/mode":
            m = b.get("mode")
            if m in ("step", "auto"):
                busmod.state["mode"] = m
                busmod.bus.emit("system", f"Mode switched to {m.upper()}.")
                busmod.set_status()
            self._json({"ok": True, "mode": busmod.state["mode"]})
        elif p == "/memory/toggle":
            mem.MEM["memory_on"] = not mem.MEM.get("memory_on", True)
            mem.save_mem()
            on = mem.MEM["memory_on"]
            busmod.bus.emit("system", "Memory ON." if on else "Memory OFF (still recording).")
            self._json({"ok": True, "memory_on": on})
        elif p == "/tts":
            if HOOKS["tts"]:
                code, ctype, payload = HOOKS["tts"](b)
                self._send(code, ctype, payload)
            else:
                self._json({"error": "tts off"}, 400)
        else:
            self._json({"error": "not found"}, 404)