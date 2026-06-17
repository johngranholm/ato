import argparse
from pathlib import Path
import urllib.request

URLS = [
    (
        "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/CesiumMan/glTF-Binary/CesiumMan.glb",
        "CesiumMan.glb",
    ),
    (
        "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/AnimatedMorphCube/glTF-Binary/AnimatedMorphCube.glb",
        "AnimatedMorphCube.glb",
    ),
]


def download(url: str, out_path: Path):
    with urllib.request.urlopen(url) as r:
        out_path.write_bytes(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="workspace/avatars")
    args = ap.parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    saved = []
    for url, name in URLS:
        out = outdir / name
        try:
            print(f"Downloading {url} -> {out}")
            download(url, out)
            print(f"Saved {out} ({out.stat().st_size} bytes)")
            saved.append(str(out))
        except Exception as e:
            print(f"Failed: {e}")

    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())
