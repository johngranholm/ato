"""Git-backed self-editing across files. Uses config.GIT so it works off-PATH."""
import os
import glob
import subprocess

from ato import config
from ato.kernel import safety
from ato.core import bus as busmod
from ato.core import memory as mem
from ato.core import archive

ROOT = config.PROJECT_ROOT
GIT = config.GIT


def _git(*args):
    try:
        return subprocess.run([GIT, "-C", ROOT, *args], capture_output=True, text=True)
    except FileNotFoundError:
        return None


def has_git():
    r = _git("rev-parse", "--is-inside-work-tree")
    return bool(r) and r.returncode == 0


def list_modules():
    out = []
    for p in glob.glob(os.path.join(config.PKG_DIR, "**", "*.py"), recursive=True):
        rel = os.path.relpath(p, config.PKG_DIR)
        out.append({"file": rel, "protected": safety.is_protected_path(p),
                    "size": os.path.getsize(p)})
    # include the UI too - it's editable and where avatar visuals live
    if os.path.exists(config.UI_HTML):
        out.append({"file": os.path.relpath(config.UI_HTML, config.PKG_DIR),
                    "protected": False, "size": os.path.getsize(config.UI_HTML)})
    return sorted(out, key=lambda d: d["file"])


def read_file(rel_path, contains=None):
    full = os.path.join(config.PKG_DIR, rel_path)
    if not safety.in_package(full):
        return "(refused: outside the ato/ package)"
    try:
        src = open(full, "r", encoding="utf-8").read()
    except Exception as e:
        return f"(could not read {rel_path}: {e})"
    if not contains:
        return src
    lines = src.splitlines()
    hits = [i for i, l in enumerate(lines) if contains in l]
    if not hits:
        return f"(no lines in {rel_path} contain {contains!r})"
    out = []
    for i in hits:
        lo, hi = max(0, i - 3), min(len(lines), i + 4)
        out.append("\n".join(f"{n+1:>5}: {lines[n]}" for n in range(lo, hi)))
    return "\n  --\n".join(out)


def edit_file(rel_path, find, replace, reason="", reboot=True):
    full = os.path.join(config.PKG_DIR, rel_path)
    if not safety.in_package(full):
        return False, "refused: path outside the ato/ package."
    if safety.is_protected_path(full):
        return False, "refused: that is the recovery harness and cannot be self-edited."
    try:
        src = open(full, "r", encoding="utf-8").read()
    except Exception as e:
        return False, f"could not read {rel_path}: {e}"
    n = src.count(find)
    if n == 0:
        return False, "find-text not present. read_file first (use 'contains') for exact text."
    if n > 1:
        return False, f"find-text is ambiguous ({n} matches). Add surrounding lines to make it unique."
    new_src = src.replace(find, replace, 1)
    if rel_path.endswith(".py"):
        try:
            compile(new_src, full, "exec")
        except SyntaxError as e:
            mem.add_crash("self-edit", f"{reason}: {e}", "self", str(e))
            return False, f"edit rejected - would break syntax (line {e.lineno}: {e.msg})"
    archive.snapshot("SELF__" + rel_path, src)        # keep the pre-edit version
    try:
        with open(full, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_src)
    except Exception as e:
        return False, f"could not write edit: {e}"
    if has_git():
        _git("add", os.path.relpath(full, ROOT))
        _git("commit", "-m", (reason or f"self-edit {rel_path}")[:200])
    busmod.bus.emit("output", f"edited {rel_path}: {reason}")
    if reboot:
        busmod.schedule_reboot(reason)
        return True, "source updated - rebooting to apply."
    return True, "source updated (no reboot yet)."


def list_versions():
    if not has_git():
        return []
    r = _git("log", "--pretty=%h\x1f%ci\x1f%s", "-n", "60")
    if not r or r.returncode != 0:
        return []
    out = []
    for line in r.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            out.append({"file": parts[0], "ts": parts[1][:16], "reason": parts[2], "thumb": None})
    return out


def rollback(to=None):
    if not has_git():
        return False, "git unavailable."
    r = _git("reset", "--hard", to) if to else _git("reset", "--hard", "HEAD~1")
    ok = bool(r) and r.returncode == 0
    return (ok, f"reset to {to or 'previous commit'}." if ok else "rollback failed.")