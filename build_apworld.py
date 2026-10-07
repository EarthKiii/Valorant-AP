"""
Package the world folder into valorant.apworld.

Equivalent to Archipelago's "Build APWorlds" launcher component, for when you don't have Archipelago's source
checked out. Usage: python build_apworld.py
"""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
WORLD = ROOT / "valorant"
OUTPUT = ROOT / "valorant.apworld"
# APContainer version, see container_version in Archipelago's worlds/Files.py.
CONTAINER_VERSION = 7
SKIPPED_PARTS = {"__pycache__", ".pytest_cache"}


def main() -> None:
    manifest = json.loads((WORLD / "archipelago.json").read_text(encoding="utf-8"))
    manifest.update(version=CONTAINER_VERSION, compatible_version=CONTAINER_VERSION)
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(WORLD.rglob("*")):
            relative = path.relative_to(ROOT)
            if path.is_dir() or SKIPPED_PARTS & set(relative.parts) or path.suffix == ".pyc":
                continue
            if path.name == "archipelago.json":
                archive.writestr(relative.as_posix(), json.dumps(manifest, indent=4))
            else:
                archive.write(path, relative.as_posix())
    print(f"Built {OUTPUT.name} (world version {manifest['world_version']})")


if __name__ == "__main__":
    main()
