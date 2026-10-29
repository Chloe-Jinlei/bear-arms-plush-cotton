"""Verify signed-hinge mathematics and optionally the actual Genesis kernel.

Run with the scene's Python environment:
  python validation/check_bending.py --runtime --output /tmp/bending-check.json

The runtime check uses the original cloth topology, a smooth wrinkle perturbation,
zero gravity, and 100 dynamic substeps; no assets or task motions are edited.
"""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from cotton_bending import build_hinges, hinge_angle_gradient


def check_math():
    rng = np.random.default_rng(7)
    max_difference = 0.0
    max_gradient_sum = 0.0
    max_torque = 0.0
    max_rigid_transform_error = 0.0
    count = 0
    for bend in (0.0, 1e-9, -0.8, 0.7, 2.7):
        p = np.array([[0., 0., 0.], [1., 0., 0.], [.3, 1., 0.],
                      [.7, -np.cos(bend), np.sin(bend)]])
        for _ in range(10):
            if bend:
                p += .01 * rng.normal(size=(4, 3))
            angle, gradient = hinge_angle_gradient(p)
            numerical = np.empty((4, 3))
            for i in range(4):
                for j in range(3):
                    plus, minus = p.copy(), p.copy()
                    plus[i, j] += 1e-6
                    minus[i, j] -= 1e-6
                    delta = hinge_angle_gradient(plus)[0] - hinge_angle_gradient(minus)[0]
                    numerical[i, j] = np.arctan2(np.sin(delta), np.cos(delta)) / 2e-6
            max_difference = max(max_difference, float(np.abs(gradient - numerical).max()))
            assert np.allclose(gradient, numerical, atol=2e-9, rtol=2e-8)
            # A gradient of a rigid-motion-invariant energy must exert neither
            # a net force nor a net torque on a free hinge.
            max_gradient_sum = max(max_gradient_sum, float(np.linalg.norm(gradient.sum(0))))
            max_torque = max(max_torque, float(np.linalg.norm(np.cross(p, gradient).sum(0))))
            q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
            if np.linalg.det(q) < 0:
                q[:, 0] *= -1
            transformed = p @ q.T + rng.normal(size=3)
            moved_angle, moved_gradient = hinge_angle_gradient(transformed)
            angle_error = np.arctan2(np.sin(moved_angle - angle), np.cos(moved_angle - angle))
            transform_error = max(abs(angle_error), float(np.abs(moved_gradient - gradient @ q.T).max()))
            max_rigid_transform_error = max(max_rigid_transform_error, transform_error)
            assert transform_error < 1e-12
            count += 1
    assert max_gradient_sum < 1e-12 and max_torque < 1e-12

    flat = np.array([[0., 0., 0.], [.01, 0., 0.], [.003, .01, 0.], [.007, -.01, 0.]])
    faces = np.array([[0, 1, 2], [1, 0, 3]])
    flat_angle, flat_gradient = hinge_angle_gradient(flat)
    assert flat_angle == 0.0 and np.isfinite(flat_gradient).all()
    assert np.linalg.norm(flat_gradient) > 0
    _, rest, compliance = build_hinges(flat, faces, 5e-5)
    _, _, scaled_compliance = build_hinges(5 * flat, faces, 5e-5)
    assert np.allclose(compliance, scaled_compliance, rtol=1e-12)

    # An independent one-hinge XPBD solve should reduce elastic energy and
    # converge to its compliant equilibrium, rather than force zero angle.
    p = flat.copy()
    p[3, 2] = .008
    angle_before = hinge_angle_gradient(p)[0]
    center_before = p.mean(0)
    weights = np.ones(4) / 1.8e-5
    alpha, multiplier = compliance[0] / .001**2, 0.0
    for _ in range(20):
        angle, gradient = hinge_angle_gradient(p)
        delta = .5 * (-angle - alpha * multiplier) / (np.sum(weights[:, None] * gradient**2) + alpha)
        multiplier += delta
        p += weights[:, None] * delta * gradient
    angle_after = hinge_angle_gradient(p)[0]
    residual = abs(angle_after + alpha * multiplier)
    assert abs(angle_after) < abs(angle_before)
    assert abs(angle_after) > .1  # Finite compliance, not a rigid flatness constraint.
    assert residual < 1e-6
    assert np.allclose(p.mean(0), center_before, atol=1e-14)

    with np.load(HERE / "assets" / "cotton.npz") as asset:
        ids, angles, _ = build_hinges(asset["points"], asset["faces"], 5e-5)
    assert len(ids) > 0 and np.max(np.abs(angles)) < 1e-12
    return {
        "passed": True,
        "finite_difference_hinges": count,
        "max_gradient_finite_difference_error": max_difference,
        "max_net_gradient": max_gradient_sum,
        "max_gradient_torque": max_torque,
        "max_rigid_transform_error": max_rigid_transform_error,
        "flat_gradient_norm": float(np.linalg.norm(flat_gradient)),
        "single_hinge_angle_before_rad": angle_before,
        "single_hinge_angle_after_rad": angle_after,
        "single_hinge_xpbd_residual": residual,
        "uniform_scale_stiffness_invariant": True,
        "original_asset_interior_hinges": len(ids),
        "original_asset_rest_angles_zero": True,
    }


def check_runtime():
    with tempfile.TemporaryDirectory(prefix="cotton-bending-check-") as temp:
        for name, child in (("GS_CACHE_FILE_PATH", "genesis"), ("XDG_CACHE_HOME", "cache"),
                            ("MPLCONFIGDIR", "matplotlib"), ("NUMBA_CACHE_DIR", "numba")):
            os.environ.setdefault(name, str(Path(temp) / child))
        import genesis as gs
        import trimesh
        from pbd_adapter import existing_pbd_mesh
        from cotton_bending import install_cotton_bending

        gs.init(backend=gs.cpu, logging_level="warning")
        with np.load(HERE / "assets" / "cotton.npz") as asset:
            points, faces = asset["points"].copy(), asset["faces"].copy()
        points[:, 2] += .3
        mesh = trimesh.Trimesh(vertices=points, faces=faces, process=False)
        mesh_path = Path(temp) / "cloth.obj"
        mesh.export(mesh_path)
        scene = gs.Scene(
            sim_options=gs.options.SimOptions(dt=.001, substeps=1, gravity=(0, 0, 0)),
            pbd_options=gs.options.PBDOptions(particle_size=.004,
                max_stretch_solver_iterations=10, max_bending_solver_iterations=4,
                hash_grid_res=(.32, .32, .32)), show_viewer=False)
        with existing_pbd_mesh("cloth", points, faces, .18 * mesh.area):
            cloth = scene.add_entity(
                material=gs.materials.PBD.Cloth(stretch_compliance=1e-7, bending_compliance=1e-5),
                morph=gs.morphs.Mesh(file=str(mesh_path), file_meshes_are_zup=True,
                                     decimate=False, convexify=False))
        bending = install_cotton_bending(scene, cloth, points, faces, 5e-5, relaxation=.5)
        try:
            bending.reset()
        except RuntimeError:
            pass
        else:
            raise AssertionError("Reset must reject uninitialized PBD fields")
        native_store = cloth.solver._kernel_store_initial_pos

        def begin_substep(f):
            native_store(f)
            bending.reset()

        cloth.solver._kernel_store_initial_pos = begin_substep
        scene.build()
        # Build-time warmup may run before the scene's public ready flag is set.
        # Once solver fields exist, resetting multipliers must still be valid.
        built_flag = scene._is_built
        try:
            scene._is_built = False
            bending.reset()
        finally:
            scene._is_built = built_flag
        initial = points.copy()
        initial[:, 2] += .006 * np.sin(2 * np.pi * points[:, 0] / .08) * np.cos(2 * np.pi * points[:, 1] / .12)
        cloth.set_particles_pos(initial)
        edges = np.asarray(cloth.edges)
        rest_lengths = np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1)
        maximum_displacement, maximum_stretch = 0.0, 0.0
        for _ in range(100):
            scene.step()
            p = cloth.get_particles_pos().cpu().numpy()
            velocity = cloth.get_particles_vel().cpu().numpy()
            assert np.isfinite(p).all() and np.isfinite(velocity).all()
            maximum_displacement = max(maximum_displacement, float(np.linalg.norm(p - initial, axis=1).max()))
            maximum_stretch = max(maximum_stretch, float((np.linalg.norm(p[edges[:, 0]] - p[edges[:, 1]], axis=1) / rest_lengths).max()))
        assert maximum_displacement < .05, maximum_displacement
        assert maximum_stretch < 1.5, maximum_stretch
        return {
            "passed": True, "backend": "CPU", "dynamic_substeps": 100,
            "substep_dt_s": .001, "particles": len(points), "triangles": len(faces),
            "bending_rigidity_N_m": 5e-5, "jacobi_relaxation": .5,
            "smooth_initial_wrinkle_amplitude_m": .006,
            "maximum_particle_displacement_m": maximum_displacement,
            "maximum_edge_stretch_ratio": maximum_stretch,
            "positions_and_velocities_finite": True,
            "reset_accepts_initialized_solver_during_scene_warmup": True,
            "reset_rejects_uninitialized_solver": True,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", action="store_true", help="Also compile and run the Genesis cloth kernel on CPU")
    parser.add_argument("--output", type=Path, help="Optional JSON result path")
    args = parser.parse_args()
    result = {"mathematics": check_math()}
    if args.runtime:
        result["genesis_runtime"] = check_runtime()
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
