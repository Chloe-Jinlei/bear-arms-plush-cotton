"""Independent material bench tests; this does not replay the dressing task.

Run with the project's Genesis interpreter. Both profiles use the original mesh,
mass, integration settings, and identical displacement-controlled test fixtures.
The only changed placement is a rigid translation of the cloth away from the
bear's table, so its original two corners can hang freely. No robot or task
trajectory is changed. These tests compare response; they are not calibration
against measured plush or cotton samples.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("both", "original", "plush_cotton"), default="both")
    parser.add_argument("--config", type=Path, default=ROOT / "config.toml")
    parser.add_argument("--original-config", type=Path, default=ROOT / "configs/original.toml")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--settle-steps", type=int, default=50)
    parser.add_argument("--compress-steps", type=int, default=30)
    parser.add_argument("--hold-steps", type=int, default=20)
    parser.add_argument("--release-steps", type=int, default=150)
    parser.add_argument("--indentation-mm", type=float, default=12.0)
    parser.add_argument("--width", type=int, default=480)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args()
    if min(args.settle_steps, args.compress_steps, args.hold_steps, args.release_steps) < 1:
        parser.error("Every phase requires at least one step")
    if not 0 < args.indentation_mm <= 30 or min(args.width, args.height) < 32:
        parser.error("Indentation must be in (0, 30] mm and resolution at least 32")
    return args


def compare(args):
    args.output.mkdir(parents=True, exist_ok=False)
    common = ["--config", str(args.config), "--original-config", str(args.original_config),
              "--backend", args.backend, "--settle-steps", str(args.settle_steps),
              "--compress-steps", str(args.compress_steps), "--hold-steps", str(args.hold_steps),
              "--release-steps", str(args.release_steps), "--indentation-mm", str(args.indentation_mm),
              "--width", str(args.width), "--height", str(args.height)]
    if args.no_render:
        common.append("--no-render")
    for profile in ("original", "plush_cotton"):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--profile", profile,
                                 "--output", str(args.output / profile), *common], check=False)
        # A failed physical check is valuable comparison evidence. A setup or
        # execution error without a completed report must still stop the run.
        if result.returncode and not (args.output/profile/"report.json").exists():
            raise RuntimeError(f"{profile} could not complete the material test")
    summarize(args.output)


def summarize(output):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    reports = {name: json.loads((output / name / "report.json").read_text())
               for name in ("original", "plush_cotton")}
    summary = {"scope": "Independent displacement-controlled material bench tests, not dressing-task validation or physical calibration",
               "profiles": {name: {"status": report["status"], "checks": report["checks"],
                                    "metrics": report["metrics"]} for name, report in reports.items()}}
    (output / "comparison.json").write_text(json.dumps(summary, indent=2))
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.5), constrained_layout=True)
    curves = [("bear_patch_indentation_mm", "Belly patch indentation", "mm"),
              ("bear_rms_speed_m_s", "Bear motion", "RMS speed (m/s)"),
              ("bear_local_volume_ratio", "Belly volume / rest volume", "ratio"),
              ("cloth_rms_speed_m_s", "Two-corner cloth drape", "RMS speed (m/s)")]
    for name, report in reports.items():
        trace = report["trace"]
        t = np.array([row["time_s"] for row in trace])
        for ax, (key, title, ylabel) in zip(axes.flat, curves):
            ax.plot(t, [row[key] for row in trace], label=name, lw=1.6)
            ax.set(title=title, xlabel="time (s)", ylabel=ylabel)
            ax.axvline(report["protocol"]["release_time_s"], color="gray", ls="--", lw=.8)
            ax.grid(alpha=.2)
    axes[0, 0].legend()
    fig.suptitle("Independent material tests · identical assets and loading · dashed line: release")
    fig.savefig(output / "comparison.png", dpi=150)
    plt.close(fig)
    print(json.dumps(summary, indent=2), flush=True)


def run(args):
    import numpy as np
    import trimesh
    from PIL import Image, ImageDraw
    import genesis as gs
    from pbd_adapter import existing_pbd_mesh, install_rigid_pbd_friction, simulation_connectivity
    from scene import read_assets, write_obj

    args.output.mkdir(parents=True, exist_ok=False)
    config_file = args.original_config if args.profile == "original" else args.config
    config = tomllib.loads(config_file.read_text())
    source_files = [*sorted((ROOT/"assets").iterdir()), ROOT/"pbd_adapter.py", ROOT/"scene.py",
                    Path(__file__).resolve(), config_file.resolve()]
    if args.profile == "plush_cotton":
        source_files.extend((ROOT/"material_response.py", ROOT/"cotton_bending.py"))
    source_hashes = {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):
                     hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files if p.is_file()}
    expected_profile = config.get("material_profile", "original")
    if expected_profile != args.profile:
        raise ValueError(f"Config profile {expected_profile!r} does not match requested {args.profile!r}")
    bcfg, ccfg, sim = config["bear"], config["cloth"], config["simulation"]
    dt = sim["substep_dt"] * sim["substeps"]
    data, mesh_dir = read_assets(config, args.output)
    bp, tetra = data["bear"]["points"], data["bear"]["tetra"]
    cp, faces = data["cotton"]["points"], data["cotton"]["faces"]
    cloth_translation = np.array([0., -.65 - cp[:, 1].mean(), 1.20 - cp[:, 2].mean()])
    cp += cloth_translation
    write_obj(mesh_dir / "cotton.obj", cp, faces, data["cotton"].get("uv"))
    rest_volumes = np.linalg.det(bp[tetra[:, 1:]] - bp[tetra[:, :1]]) / 6
    volume = float(np.abs(rest_volumes).sum())
    cloth_area = float(trimesh.Trimesh(vertices=cp, faces=faces, process=False).area)
    cloth_mass = ccfg["areal_density"] * cloth_area
    gs.init(backend=gs.cpu if args.backend == "cpu" else gs.cuda,
            seed=config["seed"], precision="32", logging_level="warning")
    start = time.perf_counter()
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=dt, substeps=sim["substeps"]),
        pbd_options=gs.options.PBDOptions(particle_size=sim["particle_size"],
            hash_grid_res=tuple(sim["hash_grid_size"]),
            max_stretch_solver_iterations=sim["stretch_iterations"],
            max_bending_solver_iterations=sim["bending_iterations"],
            max_volume_solver_iterations=sim["volume_iterations"],
            lower_bound=(-1.2, -1.2, 0), upper_bound=(1.2, 1., 2.2)),
        vis_options=gs.options.VisOptions(ambient_light=(.38, .38, .38)), show_viewer=False)
    install_rigid_pbd_friction(scene)
    th = config["table"]["height"]
    scene.add_entity(gs.morphs.Box(pos=(0, .08, th-.025), size=(.7, .5, .05), fixed=True),
        material=gs.materials.Rigid(needs_coup=True, friction=.7, coup_friction=.7),
        surface=gs.surfaces.Default(color=(.58, .43, .29, 1)))
    bear_mat = gs.materials.PBD.Elastic(rho=bcfg["mass"]/volume,
        stretch_compliance=bcfg["stretch_compliance"], volume_compliance=bcfg["volume_compliance"],
        stretch_relaxation=bcfg["stretch_relaxation"], volume_relaxation=bcfg["volume_relaxation"],
        static_friction=bcfg["friction"], kinetic_friction=bcfg.get("kinetic_friction", bcfg["friction"]))
    cloth_mat = gs.materials.PBD.Cloth(rho=ccfg["areal_density"],
        stretch_compliance=ccfg["stretch_compliance"], bending_compliance=ccfg["bending_compliance"],
        static_friction=ccfg["friction"], kinetic_friction=ccfg.get("kinetic_friction", ccfg["friction"]))
    with existing_pbd_mesh("bear", bp, tetra, bcfg["mass"]):
        bear = scene.add_entity(name="probe_bear", material=bear_mat,
            morph=gs.morphs.Mesh(file=str(mesh_dir/"bear.obj"), file_meshes_are_zup=True, decimate=False, convexify=False),
            surface=gs.surfaces.Default(diffuse_texture=gs.textures.ImageTexture(
                image_path=str(ROOT/"assets/bear_fur.png")), vis_mode="visual", roughness=1.))
    with existing_pbd_mesh("cloth", cp, faces, cloth_mass):
        cloth = scene.add_entity(name="probe_cotton", material=cloth_mat,
            morph=gs.morphs.Mesh(file=str(mesh_dir/"cotton.obj"), file_meshes_are_zup=True, decimate=False, convexify=False),
            surface=gs.surfaces.Default(diffuse_texture=gs.textures.ImageTexture(
                image_path=str(ROOT/"assets/cotton_weave.png")), vis_mode="visual", roughness=1., double_sided=True))
    material = None
    if args.profile == "plush_cotton":
        from cotton_bending import install_cotton_bending
        from material_response import install_material_response
        bending = install_cotton_bending(scene, cloth, cp, faces, ccfg["bending_rigidity_nm"])
        material = install_material_response(scene, bear, cloth, bp, tetra, cp, faces, bcfg, ccfg, bending=bending)
    cameras = {}
    if not args.no_render:
        for name, pos, lookat, fov in (
            ("bear", (.66, -.85, 1.40), (0, .065, 1.00), 37),
            ("cloth", (.85, -1.65, 1.58), (0, -.65, 1.04), 43)):
            cameras[name] = scene.add_camera(res=(args.width, args.height), GUI=False,
                                            pos=pos, lookat=lookat, fov=fov)
    scene.build()
    if material is not None:
        material.configure()
    fixed = np.flatnonzero(bp[:, 2] <= bp[:, 2].min()+bcfg["fixed_band_height"])
    bear.fix_particles(particles_idx_local=fixed, zero_velocity=True)
    cloth_corners = np.array([np.argmin(np.linalg.norm(cp - [x, cp[:, 1].min(), 1.2], axis=1))
                              for x in (cp[:, 0].min(), cp[:, 0].max())])
    cloth.fix_particles(particles_idx_local=cloth_corners, zero_velocity=True)
    surface = data["bear"]["surface_point_indices"]
    local_z = bp[:, 2]-bp[:, 2].min()
    patch = surface[(np.abs(bp[surface, 0]) < .065) & (local_z[surface] > .18)
                    & (local_z[surface] < .30) & (bp[surface, 1] < bcfg["position_xy"][1]-.065)]
    if len(patch) < 3 or np.intersect1d(fixed, patch).size:
        raise RuntimeError(f"Invalid compression patch: {patch.tolist()}")
    centers = bp[tetra].mean(axis=1)
    local_elements = ((np.abs(centers[:, 0]) < .08) &
                      (centers[:, 2] > bp[:, 2].min()+.15) & (centers[:, 2] < bp[:, 2].min()+.33))
    edges = np.asarray(cloth._edges)
    cloth_lengths = np.linalg.norm(cp[edges[:, 0]]-cp[edges[:, 1]], axis=1)
    for entity, kind, positions, topology in ((bear, "bear", bp, tetra), (cloth, "cloth", cp, faces)):
        assert np.allclose(entity.get_particles_pos().cpu().numpy(), positions, atol=2e-7, rtol=0)
        assert np.array_equal(np.sort(simulation_connectivity(entity, kind), axis=1), np.sort(topology, axis=1))
    particle_masses = scene.sim.pbd_solver.particles_info.mass.to_numpy()
    verified_masses = {name: float(particle_masses[e._particle_start:e._particle_start+e.n_particles].astype(np.float64).sum())
                       for name, e in (("bear", bear), ("cloth", cloth))}
    assert np.isclose(verified_masses["bear"], bcfg["mass"], rtol=1e-6)
    assert np.isclose(verified_masses["cloth"], cloth_mass, rtol=1e-6)
    protocol = {"settle_steps": args.settle_steps, "compress_steps": args.compress_steps,
        "hold_steps": args.hold_steps, "release_steps": args.release_steps,
        "indentation_m": args.indentation_mm/1000, "step_dt_s": dt,
        "release_time_s": (args.settle_steps+args.compress_steps+args.hold_steps)*dt,
        "patch_indices": patch.tolist(), "bear_fixed_indices": fixed.tolist(),
        "cloth_corner_indices": cloth_corners.tolist(), "cloth_translation_m": cloth_translation.tolist(),
        "loading": "Smooth displacement-controlled front belly patch, then zero-velocity release; no applied-force calibration",
        "cloth_loading": "Gravity-driven drape from an initially flat sheet; only two original corners fixed"}
    trace, step_times, saved_bear, saved_cloth, saved_steps = [], [], [], [], []
    reference = None
    phase_ends = np.cumsum([args.settle_steps, args.compress_steps, args.hold_steps, args.release_steps])
    keyframes = {0: "initial", int(phase_ends[0]): "settled", int(phase_ends[1]): "compressed",
                 int(phase_ends[2]): "release", int(phase_ends[2])+1: "release-first-step",
                 int(phase_ends[-1]): "recovered"}

    def record(step, phase):
        p, v = bear.get_particles_pos().cpu().numpy(), bear.get_particles_vel().cpu().numpy()
        c, cv = cloth.get_particles_pos().cpu().numpy(), cloth.get_particles_vel().cpu().numpy()
        if not all(np.isfinite(x).all() for x in (p, v, c, cv)):
            raise RuntimeError(f"Non-finite state at step {step}")
        volumes = np.linalg.det(p[tetra[:, 1:]].astype(np.float64)-p[tetra[:, :1]].astype(np.float64))/6
        ratios = volumes/rest_volumes
        strain = np.linalg.norm(c[edges[:, 0]]-c[edges[:, 1]], axis=1)/cloth_lengths-1
        ref = bp if reference is None else reference
        row = {"step": step, "phase": phase, "time_s": step*dt,
            "bear_height_ratio": float(np.ptp(p[:, 2])/np.ptp(bp[:, 2])),
            "bear_rms_speed_m_s": float(np.sqrt(np.mean(np.sum(v*v, axis=1)))),
            "bear_max_displacement_m": float(np.linalg.norm(p-bp, axis=1).max()),
            "bear_base_drift_m": float(np.linalg.norm(p[fixed]-bp[fixed], axis=1).max()),
            "bear_patch_indentation_mm": float(np.mean(p[patch, 1]-ref[patch, 1])*1000),
            "bear_volume_ratio": float(np.sum(np.abs(rest_volumes)*ratios)/np.abs(rest_volumes).sum()),
            "bear_local_volume_ratio": float(np.sum(np.abs(rest_volumes[local_elements])*ratios[local_elements])/np.abs(rest_volumes[local_elements]).sum()),
            "bear_min_tetra_volume_ratio": float(ratios.min()), "bear_inverted_tetrahedra": int((ratios<=0).sum()),
            "cloth_rms_speed_m_s": float(np.sqrt(np.mean(np.sum(cv*cv, axis=1)))),
            "cloth_max_extension_fraction": float(strain.max()),
            "cloth_p95_abs_edge_strain": float(np.percentile(np.abs(strain), 95)),
            "cloth_drop_m": float(cp[:, 2].mean()-c[:, 2].mean()),
            "cloth_anchor_drift_m": float(np.linalg.norm(c[cloth_corners]-cp[cloth_corners], axis=1).max())}
        trace.append(row)
        if step%5 == 0 or step in keyframes:
            saved_steps.append(step); saved_bear.append(p.copy()); saved_cloth.append(c.copy())
        if step in keyframes:
            for name, camera in cameras.items():
                rgb, *_ = camera.render()
                im = Image.fromarray(rgb)
                draw = ImageDraw.Draw(im)
                draw.rectangle((0, 0, args.width, 32), fill=(245, 245, 245))
                draw.text((7, 4), f"{args.profile} | {name} | {keyframes[step]} | {step*dt:.2f}s", fill=(20, 20, 20))
                draw.text((7, 18), "Independent material test (not the dressing task)", fill=(55, 55, 55))
                im.save(args.output/f"{step:04d}-{keyframes[step]}-{name}.png")
        return row

    try:
        record(0, "initial")
        for step in range(1, int(phase_ends[-1])+1):
            if step <= phase_ends[0]:
                phase = "settle"
            elif step <= phase_ends[1]:
                phase = "compress"
                if step == phase_ends[0]+1:
                    reference = bear.get_particles_pos().cpu().numpy().copy()
                    bear.fix_particles(particles_idx_local=patch, zero_velocity=True)
                f = (step-phase_ends[0])/args.compress_steps
                smooth = f*f*(3-2*f)
                targets = reference[patch].copy(); targets[:, 1] += smooth*args.indentation_mm/1000
                bear.set_particles_pos(targets, particles_idx_local=patch)
            elif step <= phase_ends[2]:
                phase = "hold"
            else:
                phase = "release"
                if step == phase_ends[2]+1:
                    bear.release_particle(particles_idx_local=patch)
            before = time.perf_counter(); scene.step(); step_times.append(time.perf_counter()-before)
            row = record(step, phase)
            if step%50 == 0:
                print(f"{args.profile}: {step}/{phase_ends[-1]} {phase}; height={row['bear_height_ratio']:.4f}, inverted={row['bear_inverted_tetrahedra']}", flush=True)
        released = [row for row in trace if row["phase"] == "release"]
        tail = released[-min(30, len(released)):]
        metrics = {"final_bear_height_ratio": trace[-1]["bear_height_ratio"],
            "release_peak_bear_rms_speed_m_s": max(r["bear_rms_speed_m_s"] for r in released),
            "release_tail_mean_bear_rms_speed_m_s": statistics.mean(r["bear_rms_speed_m_s"] for r in tail),
            "release_tail_patch_peak_to_peak_mm": max(r["bear_patch_indentation_mm"] for r in tail)-min(r["bear_patch_indentation_mm"] for r in tail),
            "release_integrated_bear_mean_squared_speed_m2_s": sum(r["bear_rms_speed_m_s"]**2*dt for r in released),
            "release_tail_mean_cloth_rms_speed_m_s": statistics.mean(r["cloth_rms_speed_m_s"] for r in tail),
            "max_bear_base_drift_m": max(r["bear_base_drift_m"] for r in trace),
            "max_inverted_tetrahedra": max(r["bear_inverted_tetrahedra"] for r in trace),
            "min_local_volume_ratio": min(r["bear_local_volume_ratio"] for r in trace),
            "final_patch_indentation_mm": trace[-1]["bear_patch_indentation_mm"],
            "max_cloth_extension_fraction": max(r["cloth_max_extension_fraction"] for r in trace),
            "peak_cloth_p95_abs_edge_strain": max(r["cloth_p95_abs_edge_strain"] for r in trace),
            "final_cloth_p95_abs_edge_strain": trace[-1]["cloth_p95_abs_edge_strain"],
            "max_cloth_anchor_drift_m": max(r["cloth_anchor_drift_m"] for r in trace),
            "mean_step_seconds": statistics.mean(step_times), "wall_seconds": time.perf_counter()-start}
        checks = {"finite_states": True, "base_fixed": metrics["max_bear_base_drift_m"] < 1e-6,
                  "cloth_corners_fixed": metrics["max_cloth_anchor_drift_m"] < 1e-6,
                  "no_inverted_tetrahedra": metrics["max_inverted_tetrahedra"] == 0,
                  "geometry_topology_mass_preserved": True}
        report = {"status": "passed" if all(checks.values()) else "failed", "profile": args.profile,
            "scope": "Independent displacement-controlled material tests; no robot, no dressing trajectory, not calibrated to measured samples",
            "config": config, "protocol": protocol, "metrics": metrics, "checks": checks,
            "verified_masses_kg": verified_masses,
            "source_sha256_at_start": source_hashes,
            "trace": trace}
        if material is not None:
            report["material_response"] = material.description
        (args.output/"report.json").write_text(json.dumps(report, indent=2))
        np.savez_compressed(args.output/"trajectory.npz", steps=np.array(saved_steps),
                            bear_positions=np.array(saved_bear), cloth_positions=np.array(saved_cloth),
                            bear_tetra=tetra, cloth_faces=faces, patch_indices=patch,
                            fixed_indices=fixed, cloth_corner_indices=cloth_corners)
        print(json.dumps({"profile": args.profile, "checks": checks, "metrics": metrics}, indent=2), flush=True)
        if not all(checks.values()):
            raise RuntimeError(f"Material test checks failed: {checks}")
    finally:
        gs.destroy()


def main():
    args = arguments()
    os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
    os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    os.environ.setdefault("QD_NUM_THREADS", "2")
    cache = Path(os.environ.get("BEAR_CACHE_DIR", "/tmp/bear-material-probe-cache"))
    for key, sub in (("XDG_CACHE_HOME", ""), ("GS_CACHE_FILE_PATH", "genesis"),
                     ("NUMBA_CACHE_DIR", "numba"), ("MPLCONFIGDIR", "matplotlib")):
        os.environ.setdefault(key, str(cache/sub))
    if args.profile == "both":
        compare(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
