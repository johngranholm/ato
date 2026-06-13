"""
Safety boundary. KERNEL FILE - never self-edited.

Enforces:
  * is_dangerous   - regex denylist of catastrophic commands
  * is_interactive_repl - blocks bare interpreters that would hang the agent
  * in_workdir     - confines write_file targets to A.T.O.'s workspace
  * is_protected_path - refuses self-edits to any kernel file (the real
                        invariant; soft prompt rules are not enough)
"""
import os
import re

from ato import config

# ------------------------------------------------------------------ denylist
DANGEROUS = [
    r"rm\s+-rf", r"rm\s+-[a-z]*f", r"\brm\s+-r\b", r"\bmkfs\b", r"\bdd\s+if=",
    r">\s*/dev/sd", r"/dev/sd[a-z]", r":\(\)\s*\{.*\}", r"\bshutdown\b",
    r"\breboot\b", r"\bpoweroff\b", r"\bhalt\b", r"curl\s+.*\|\s*(bash|sh)",
    r"wget\s+.*\|\s*(bash|sh)", r"wsl\s+--unregister", r"wsl\s+--shutdown",
    r"\bdiskpart\b", r"\bfdisk\b", r"format\s+[a-zA-Z]:", r"del\s+/[sq]",
    r"rmdir\s+/s", r"\bdeltree\b", r"chmod\s+-R\s+777\s+/", r"\bfsutil\b",
    r"cipher\s+/w", r"\btakeown\b.*/[rR]",
]
DANGER_RE = [re.compile(p, re.IGNORECASE) for p in DANGEROUS]


def is_dangerous(cmd: str) -> bool:
    return any(rx.search(cmd) for rx in DANGER_RE)


# -------------------------------------------------------- interactive guard
def is_interactive_repl(cmd: str) -> bool:
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


# ------------------------------------------------------------- path jails
def _abspath(path: str, root: str) -> str:
    return os.path.abspath(path) if os.path.isabs(path) else os.path.abspath(os.path.join(root, path))


def in_workdir(path: str) -> bool:
    """True if `path` resolves inside A.T.O.'s workspace (where it may write/run)."""
    full = _abspath(path, config.WORKDIR)
    root = os.path.abspath(config.WORKDIR)
    try:
        return os.path.commonpath([full, root]) == root
    except ValueError:                      # different drive on Windows
        return False


def in_package(path: str) -> bool:
    """True if `path` resolves inside the ato/ package (where self-edits land)."""
    full = _abspath(path, config.PKG_DIR)
    root = os.path.abspath(config.PKG_DIR)
    try:
        return os.path.commonpath([full, root]) == root
    except ValueError:
        return False


# --------------------------------------------------- KERNEL PROTECTION
# These files define the boundary. A.T.O. can READ them but edit_file()
# MUST refuse to modify them. This is the enforced invariant that replaces
# the old "please don't edit the safety list" prompt instruction.
PROTECTED_RELATIVE = {
    "__main__.py",
    "config.py",
    "supervisor.py",
    os.path.join("kernel", "__init__.py"),
    os.path.join("kernel", "safety.py"),
    os.path.join("kernel", "server.py"),       # arrives in Module 2
    os.path.join("kernel", "bootstrap.py"),    # arrives in Module 2
}
PROTECTED_ABS = {os.path.abspath(os.path.join(config.PKG_DIR, p)) for p in PROTECTED_RELATIVE}


def is_protected_path(path: str) -> bool:
    """True if `path` is a kernel file that must never be self-edited."""
    full = _abspath(path, config.PKG_DIR)
    if full in PROTECTED_ABS:
        return True
    # belt-and-suspenders: protect the whole kernel/ directory
    kdir = os.path.abspath(os.path.join(config.PKG_DIR, "kernel"))
    try:
        return os.path.commonpath([full, kdir]) == kdir
    except ValueError:
        return False