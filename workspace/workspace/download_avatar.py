import argparse
from pathlib import Path
import urllib.request

URLS = [
    "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/DamagedHelmet/glTF-Binary/DamagedHelmet.glb",
    "https://github.com/KhronosGroup/glTF-Sample-Assets/raw/main/Models/DamagedHelmet/glTF-Binary/DamagedHelmet.glb",
]


def download(url: str, out_path: Path):
    with urllib.request.urlopen(url) as r:
        out_path.write_bytes(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="workspace/avatar.glb")
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    for url in URLS:
        try:
            print(f"Downloading {url} -> {out}")
            download(url, out)
            print(f"Saved {out} ({out.stat().st_size} bytes)")
            return 0
        except Exception as e:
            print(f"Failed: {e}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
