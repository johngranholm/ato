"""
Safety boundary. KERNEL FILE - never self-edited.
With config.RESTRICTIONS = False the command denylist and path jail are OFF.
Only the recovery harness (supervisor + entry point) stays protected so the
system can always recover from a bad edit.
"""
import os
import re

from ato import config

DANGEROUS = [
    r"rm\s+-rf", r"\bmkfs\b", r"\bdd\s+if=", r"format\s+[a-zA-Z]:",
    r"wsl\s+--unregister",
]
DANGER_RE = [re.compile(p, re.IGNORECASE) for p in DANGEROUS]


def is_dangerous(cmd: str) -> bool:
    if not config.RESTRICTIONS:
        return False
    return any(rx.search(cmd) for rx in DANGER_RE)


def is_interactive_repl(cmd: str) -> bool:
    # kept always-on: a bare interpreter hangs the agent regardless of policy
    c = cmd.strip()
    c = re.sub(r"^\s*wsl\s+(bash\s+-lc\s+)?", "", c, flags=re.IGNORECASE).strip().strip('"').strip("'")
    toks = c.split()
    if not toks:
        return False
    base = os.path.basename(toks[0]).lower()
    interpreters = {"python", "python3", "ipython", "node", "irb",
                    "python.exe", "python3.exe"}
    if base in interpreters and len(toks) == 1:
        return True
    if base in interpreters and "-i" in toks:
        return True
    return False


def _abspath(path, root):
    return os.path.abspath(path) if os.path.isabs(path) else os.path.abspath(os.path.join(root, path))


def in_workdir(path: str) -> bool:
    if not config.RESTRICTIONS:
        return True                      # no jail
    full = _abspath(path, config.WORKDIR)
    root = os.path.abspath(config.WORKDIR)
    try:
        return os.path.commonpath([full, root]) == root
    except ValueError:
        return False


def in_package(path: str) -> bool:
    full = _abspath(path, config.PKG_DIR)
    root = os.path.abspath(config.PKG_DIR)
    try:
        return os.path.commonpath([full, root]) == root
    except ValueError:
        return False


# Always protected: the recovery harness. If these break and git rollback is
# unavailable, the system can't recover. Everything else is self-editable when
# config.ALLOW_KERNEL_EDIT is True.
NEVER_EDIT = {
    os.path.abspath(os.path.join(config.PKG_DIR, "supervisor.py")),
    os.path.abspath(os.path.join(config.PKG_DIR, "__main__.py")),
}
PROTECTED_RELATIVE = {
    "__main__.py", "config.py", "supervisor.py",
    os.path.join("kernel", "__init__.py"),
    os.path.join("kernel", "safety.py"),
    os.path.join("kernel", "server.py"),
    os.path.join("kernel", "bootstrap.py"),
}
PROTECTED_ABS = {os.path.abspath(os.path.join(config.PKG_DIR, p)) for p in PROTECTED_RELATIVE}


def is_protected_path(path: str) -> bool:
    full = _abspath(path, config.PKG_DIR)
    if full in NEVER_EDIT:
        return True                      # recovery harness - never editable
    if config.ALLOW_KERNEL_EDIT:
        return False                     # everything else is fair game
    if full in PROTECTED_ABS:
        return True
    kdir = os.path.abspath(os.path.join(config.PKG_DIR, "kernel"))
    try:
        return os.path.commonpath([full, kdir]) == kdir
    except ValueError:
        return False