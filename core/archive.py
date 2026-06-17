"""
Versioned archive of every script A.T.O. writes. Timestamped, dependency-free.
Solves 'it worked then broke next run' - every version is recoverable.
"""
import os
import time
import glob

from ato import config


def _dir_for(rel_path):
    safe = rel_path.replace("\\", "__").replace("/", "__")
    d = os.path.join(config.ARCHIVE_DIR, safe)
    os.makedirs(d, exist_ok=True)
    return d


def snapshot(rel_path, content):
    """Save a timestamped copy. Called on every write_file."""
    try:
        d = _dir_for(rel_path)
        ts = time.strftime("%Y%m%d-%H%M%S")
        with open(os.path.join(d, ts + ".txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(content if content is not None else "")
        return True
    except Exception:
        return False


def list_versions(rel_path):
    d = _dir_for(rel_path)
    return sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(d, "*.txt")))


def read_version(rel_path, ts):
    p = os.path.join(_dir_for(rel_path), ts + ".txt")
    try:
        return open(p, "r", encoding="utf-8").read()
    except Exception:
        return None