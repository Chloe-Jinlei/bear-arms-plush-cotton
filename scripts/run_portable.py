#!/usr/bin/env python3
"""Run the unchanged scene with repository-local Panda assets.

Uses the interpreter that launches this script. Defaults match run-wrap.sh:
--task wrap --steps 50 --stop-after thread_arms. Later user arguments override
these defaults. Relative --config, --output and --resume paths are interpreted
from the caller's working directory, before selecting the asset search directory.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "vendor" / "genesis-assets"
PANDA = ASSET_ROOT / "xml" / "franka_emika_panda"
DEFAULT_ARGUMENTS = ["--task", "wrap", "--steps", "50", "--stop-after", "thread_arms"]
PATH_ARGUMENTS = {"--config", "--output", "--resume"}


def absolute_path(value: str, caller: Path) -> str:
    path = Path(value).expanduser()
    return str((path if path.is_absolute() else caller / path).resolve())


def absolute_arguments(arguments: list[str], caller: Path) -> list[str]:
    """Preserve all arguments while resolving explicit user file paths."""
    result = list(arguments)
    index = 0
    while index < len(result):
        option, separator, value = result[index].partition("=")
        if option in PATH_ARGUMENTS:
            if separator:
                result[index] = option + "=" + absolute_path(value, caller)
            elif index + 1 < len(result) and not result[index + 1].startswith("--"):
                index += 1
                result[index] = absolute_path(result[index], caller)
        index += 1
    return result


def configure_environment(arguments: list[str], caller: Path) -> None:
    # This must precede imports of MuJoCo, OpenGL or Genesis.
    if "--headless" in arguments:
        os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    cache = Path(absolute_path(os.environ.get("BEAR_CACHE_DIR", str(ROOT / ".cache")), caller))
    os.environ["BEAR_CACHE_DIR"] = str(cache)
    for key, suffix in (("GS_CACHE_FILE_PATH", "genesis"), ("XDG_CACHE_HOME", ""),
                        ("NUMBA_CACHE_DIR", "numba"), ("MPLCONFIGDIR", "matplotlib")):
        os.environ[key] = absolute_path(os.environ.get(key, str(cache / suffix)), caller)


def check_assets(robot_geometry) -> None:
    """Compile the planner's vendored MuJoCo model without simulation or output files."""
    entry = PANDA / "panda.xml"
    xml = ET.parse(entry).getroot()
    meshes = xml.findall("./asset/mesh[@file]")
    mesh_directory = entry.parent / xml.find("compiler").get("meshdir", "")
    missing = [str(mesh_directory / node.get("file")) for node in meshes
               if not (mesh_directory / node.get("file")).is_file()]
    if len(meshes) != 67 or missing:
        raise RuntimeError(f"Expected 67 complete Panda mesh assets; found {len(meshes)}, missing={missing}")
    genesis_entry = Path("xml/franka_emika_panda/panda.xml").resolve()
    if genesis_entry != entry.resolve():
        raise RuntimeError("Genesis relative asset lookup does not resolve to the vendored Panda")
    model, _ = robot_geometry.make_model()
    if model.nmesh != 67:
        raise RuntimeError(f"Planner compiled {model.nmesh} meshes; expected 67")
    print(json.dumps({"status": "passed", "scope": "Asset loading only; no physics simulation",
        "planner_asset_directory": str(robot_geometry.ASSET),
        "genesis_relative_asset_resolves_to": str(genesis_entry),
        "mesh_files": len(meshes), "compiled_meshes": int(model.nmesh),
        "compiled_textures": int(model.ntex)}, indent=2))


def main(argv: list[str] | None = None):
    caller = Path.cwd()
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False, description=__doc__)
    parser.add_argument("--check-assets", action="store_true",
                        help="Load all 67 Panda meshes with MuJoCo and exit without running physics")
    wrapper, remaining = parser.parse_known_args(arguments)
    configure_environment(remaining, caller)
    sys.path.insert(0, str(ROOT))

    if "--help" in remaining or "-h" in remaining:
        print(__doc__)
        print("\nPortable-only option: --check-assets (read-only model loading).\n")
        import scene
        sys.argv = [str(Path(__file__).resolve()), *DEFAULT_ARGUMENTS, *remaining]
        return scene.main()

    if not (PANDA / "panda.xml").is_file():
        parser.error(f"Vendored Panda model is missing: {PANDA / 'panda.xml'}")
    forwarded = absolute_arguments(remaining, caller)
    import robot_geometry
    robot_geometry.ASSET = PANDA
    os.chdir(ASSET_ROOT)
    if wrapper.check_assets:
        check_assets(robot_geometry)
        return 0

    import scene
    sys.argv = [str(Path(__file__).resolve()), *DEFAULT_ARGUMENTS, *forwarded]
    return scene.main()


if __name__ == "__main__":
    sys.exit(main())
