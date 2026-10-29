"""Verify that the material update preserves the supplied assets and actions."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "abe0008c9331e1d3d875c73916008af7d612186b"
PROTECTED = [
    "arm_geometry.py", "arms_task.py", "asset_primitives.py", "generate_assets.py",
    "robot_geometry.py", "seam_surface_contact.py", "velcro_contact.py",
    "velcro_plan.json", "wrap_plan.json", "wrap_contact.py", "wrap_task.py",
    "pbd_adapter.py", "run.sh", "run-wrap.sh",
]


def verify():
    original = tomllib.loads((ROOT / "configs/original.toml").read_text())
    current = tomllib.loads((ROOT / "config.toml").read_text())
    allowed = {
        "bear": {"stretch_compliance", "volume_compliance", "stretch_relaxation",
                 "volume_relaxation", "friction", "kinetic_friction",
                 "bulk_modulus_compression_pa", "bulk_modulus_expansion_pa",
                 "internal_stretch_compliance", "surface_stretch_compliance",
                 "internal_damping_per_s", "bulk_relaxation", "minimum_volume_ratio",
                 "maximum_volume_correction_m", "shape_damping_per_s"},
        "cloth": {"stretch_compliance", "bending_compliance", "friction",
                  "kinetic_friction", "bending_rigidity_nm", "internal_damping_per_s",
                  "air_density_kg_m3", "air_drag_coefficient", "warp_max_extension",
                  "weft_max_extension", "bias_max_extension", "strain_limit_iterations"},
    }
    stripped = {}
    for name, config in (("original", original), ("current", current)):
        config.pop("material_profile", None)
        for section, keys in allowed.items():
            config[section] = {k: v for k, v in config[section].items() if k not in keys}
        stripped[name] = config
    records = []
    paths = PROTECTED + [str(p.relative_to(ROOT)) for p in sorted((ROOT / "assets").iterdir()) if p.is_file()]
    for relative in paths + ["configs/original.toml"]:
        original_path = "config.toml" if relative == "configs/original.toml" else relative
        source = subprocess.check_output(["git", "show", f"{BASELINE}:{original_path}"], cwd=ROOT)
        actual = (ROOT / relative).read_bytes()
        records.append({"path": relative, "unchanged": source == actual,
                        "sha256": hashlib.sha256(actual).hexdigest()})
    checks = {"assets_and_action_files_unchanged": all(r["unchanged"] for r in records),
              "only_material_configuration_changed": stripped["original"] == stripped["current"]}
    return {"baseline_commit": BASELINE, "status": "passed" if all(checks.values()) else "failed",
            "checks": checks, "files": records}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, indent=2))
    raise SystemExit(0 if report["status"] == "passed" else 1)
