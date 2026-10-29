"""Repeatable CPU checks of the scene-local material kernels.

The inputs are deliberately artificial: a 5 cm tetrahedron of mass 20 g and a
5 cm square cloth patch of mass 0.45 g, with zero gravity.  Tests prescribe
velocities and a temporary 20% axial compression to isolate material response.
These fixtures are not changes to the bear/cloth assets or the task controller,
and passing these checks does not calibrate a real plush toy or cotton sample.

Run using the scene's Genesis environment:
  python validation/check_material_response.py --output /tmp/material-check.json
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


def _write_obj(path, vertices, faces):
    path.write_text("\n".join(
        ["v " + " ".join(map(str, row)) for row in vertices]
        + ["f " + " ".join(map(str, row + 1)) for row in faces]) + "\n")


def check_runtime():
    with tempfile.TemporaryDirectory(prefix="material-response-check-") as temp:
        root = Path(temp)
        for name, child in (("GS_CACHE_FILE_PATH", "genesis"), ("XDG_CACHE_HOME", "cache"),
                            ("MPLCONFIGDIR", "matplotlib"), ("NUMBA_CACHE_DIR", "numba")):
            os.environ.setdefault(name, str(root / child))
        import genesis as gs
        from pbd_adapter import existing_pbd_mesh
        from material_response import install_material_response

        body_points = np.array([[0., 0., .5], [.05, 0., .5], [0., .05, .5],
                                [0., 0., .55]], dtype=np.float32)
        tetra = np.array([[0, 1, 2, 3]], dtype=np.int32)
        body_faces = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])
        cloth_points = np.array([[.2, 0., .5], [.25, 0., .5], [.25, .05, .5],
                                 [.2, .05, .5]], dtype=np.float32)
        cloth_faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
        body_path, cloth_path = root / "tetra.obj", root / "cloth.obj"
        _write_obj(body_path, body_points, body_faces)
        _write_obj(cloth_path, cloth_points, cloth_faces)
        gs.init(backend=gs.cpu, logging_level="warning", seed=7)
        scene = gs.Scene(
            sim_options=gs.options.SimOptions(dt=.001, substeps=1, gravity=(0, 0, 0)),
            pbd_options=gs.options.PBDOptions(particle_size=.002, max_volume_solver_iterations=10),
            vis_options=gs.options.VisOptions(n_support_neighbors=4), show_viewer=False)
        with existing_pbd_mesh("bear", body_points, tetra, .02):
            bear = scene.add_entity(
                gs.morphs.Mesh(file=str(body_path), decimate=False, convexify=False),
                material=gs.materials.PBD.Elastic())
        with existing_pbd_mesh("cloth", cloth_points, cloth_faces, .00045):
            cloth = scene.add_entity(
                gs.morphs.Mesh(file=str(cloth_path), decimate=False, convexify=False),
                material=gs.materials.PBD.Cloth())
        adapter = install_material_response(
            scene, bear, cloth, body_points, tetra, cloth_points, cloth_faces,
            {"shape_damping_per_s": 20.0}, {})
        # Also exercises automatic configuration during Genesis's build warmup.
        scene.build()
        adapter.configure()

        def velocities():
            return np.concatenate([bear.get_particles_vel().cpu().numpy(),
                                   cloth.get_particles_vel().cpu().numpy()]).astype(np.float64)

        def set_velocities(value):
            bear.set_particles_vel(np.asarray(value[:4], dtype=np.float32))
            cloth.set_particles_vel(np.asarray(value[4:], dtype=np.float32))

        def damp():
            adapter.damp_edges(adapter.edges, adapter.rates)
            adapter.damp_shape()

        points = np.concatenate([body_points, cloth_points]).astype(np.float64)
        translation = np.tile([.2, -.4, .1], (len(points), 1))
        rotation = np.cross(np.array([.3, -.7, .9]), points - points.mean(axis=0))
        rigid_errors = {}
        for name, value in (("translation", translation), ("rotation", rotation),
                            ("translation_and_rotation", translation + rotation)):
            set_velocities(value)
            before = velocities()
            damp()
            error = float(np.abs(velocities() - before).max())
            rigid_errors[name] = error
            assert error < 2e-7, f"Damping changed rigid {name}: {error} m/s"

        rng = np.random.default_rng(7)
        set_velocities(rng.normal(size=points.shape))
        before = velocities()
        masses = scene.sim.pbd_solver.particles_info.mass.to_numpy().astype(np.float64)
        center = (masses[:, None] * points).sum(axis=0) / masses.sum()

        def energy(velocity):
            return float(.5 * (masses[:, None] * velocity**2).sum())

        def linear_momentum(velocity):
            return (masses[:, None] * velocity).sum(axis=0)

        def angular_momentum(velocity):
            return np.cross(points - center, masses[:, None] * velocity).sum(axis=0)

        damp()
        after = velocities()
        energy_before, energy_after = energy(before), energy(after)
        linear_error = float(np.linalg.norm(linear_momentum(after) - linear_momentum(before)))
        angular_error = float(np.linalg.norm(angular_momentum(after) - angular_momentum(before)))
        assert 0 < energy_after < energy_before
        assert linear_error < 2e-8 and angular_error < 2e-8

        # Uniform expansion is a pure non-rigid velocity mode.  The rigid fit
        # must remove exactly the requested fraction of its velocity, whereas
        # the translation/rotation checks above must remain unchanged.
        expansion = 3.0 * (body_points.astype(np.float64) - body_points.mean(axis=0))
        bear.set_particles_vel(expansion)
        expansion_before = bear.get_particles_vel().cpu().numpy().astype(np.float64)
        adapter.damp_shape()
        expansion_after = bear.get_particles_vel().cpu().numpy().astype(np.float64)
        expected_shape_factor = float(np.exp(-20.0 * .001))
        expansion_error = float(np.abs(expansion_after - expected_shape_factor * expansion_before).max())
        assert expansion_error < 2e-7

        compressed = body_points.copy()
        compressed[:, 0] *= .8
        bear.set_particles_pos(compressed)
        set_velocities(np.zeros_like(points))
        rest_determinant = np.linalg.det(body_points[tetra[:, 1:]] - body_points[tetra[:, :1]])[0]

        def volume_ratio():
            current = bear.get_particles_pos().cpu().numpy()
            return float(np.linalg.det(current[tetra[:, 1:]] - current[tetra[:, :1]])[0]
                         / rest_determinant)

        j_before = volume_ratio()
        adapter.reset()
        adapter.solve_volume(0)
        j_first = volume_ratio()
        lambda_first = float(adapter.lambda_bulk.to_numpy()[0, 0])
        adapter.solve_volume(0)
        j_repeat = volume_ratio()
        lambda_repeat = float(adapter.lambda_bulk.to_numpy()[0, 0])
        assert j_before < j_first < .9, "Finite-compliance solve must recover partly, not force J=1"
        assert lambda_first != 0 and lambda_repeat != 0
        assert abs(j_repeat - j_first) < 1e-5, "Repeated volume pass must preserve XPBD multipliers"
        # A deliberately erroneous reset demonstrates this check can detect
        # extra stiffening if contact re-solves start from lambda=0 each time.
        adapter.reset()
        adapter.solve_volume(0)
        j_with_deliberate_reset = volume_ratio()
        assert j_with_deliberate_reset - j_repeat > 1e-4
        adapter.store_initial(0)
        assert np.all(adapter.lambda_bulk.to_numpy() == 0)
        scene.step()
        assert np.isfinite(bear.get_particles_pos().cpu().numpy()).all()
        assert np.isfinite(cloth.get_particles_pos().cpu().numpy()).all()

        # A nonzero prescribed velocity stands in for the kinematic velocity of
        # a pinned/attached node; damping must not rewrite that node's velocity.
        # Run last: this PBD-only fixture has no rigid-link attachment buffers.
        bear.fix_particles(particles_idx_local=np.array([0]), zero_velocity=False)
        set_velocities(rng.normal(size=points.shape))
        fixed_before = velocities()[0].copy()
        current_points = np.concatenate([bear.get_particles_pos().cpu().numpy(),
                                         cloth.get_particles_pos().cpu().numpy()]).astype(np.float64)
        free_body = np.array([1, 2, 3])
        free_mass = masses[free_body]
        free_center = (free_mass[:, None] * current_points[free_body]).sum(axis=0) / free_mass.sum()
        free_before = velocities()[free_body]
        adapter.damp_shape()
        free_after = velocities()[free_body]
        free_momentum_error = float(np.linalg.norm((free_mass[:, None] * (free_after - free_before)).sum(axis=0)))
        free_angular_error = float(np.linalg.norm(np.cross(
            current_points[free_body] - free_center, free_mass[:, None] * (free_after - free_before)).sum(axis=0)))
        assert free_momentum_error < 2e-8 and free_angular_error < 2e-8
        fixed_error = float(np.abs(velocities()[0] - fixed_before).max())
        assert fixed_error == 0.0
        adapter.damp_edges(adapter.edges, adapter.rates)
        assert float(np.abs(velocities()[0] - fixed_before).max()) == 0.0
        # With only one free node there is no non-rigid velocity to dissipate.
        bear.fix_particles(particles_idx_local=np.array([1, 2]), zero_velocity=False)
        degenerate_before = velocities().copy()
        adapter.damp_shape()
        degenerate_error = float(np.abs(velocities() - degenerate_before).max())
        assert degenerate_error == 0.0

        actual_air_sum = float(scene.sim.pbd_solver.particles_info.air_resistance.to_numpy()[
            cloth.particle_start:cloth.particle_end].sum(dtype=np.float64))
        expected_air_sum = .5 * 1.225 * (.05 * .05)
        assert np.isclose(actual_air_sum, expected_air_sum, rtol=1e-6)
        return {
            "passed": True, "backend": "cpu", "substep_dt_s": .001,
            "artificial_fixture": {
                "body": "one 5 cm tetrahedron, 20 g", "cloth": "5 cm square, 0.45 g",
                "gravity_m_per_s2": [0, 0, 0], "temporary_axial_compression_fraction": .20,
                "production_assets_or_controller_changed": False},
            "rigid_motion_velocity_error_m_per_s": rigid_errors,
            "free_damping": {
                "kinetic_energy_before_J": energy_before, "kinetic_energy_after_J": energy_after,
                "kinetic_energy_ratio": energy_after / energy_before,
                "linear_momentum_error_kg_m_per_s": linear_error,
                "angular_momentum_error_kg_m2_per_s": angular_error},
            "fixed_velocity_error_m_per_s": fixed_error,
            "bear_shape_damping": {
                "rate_per_s": 20.0, "pure_expansion_expected_velocity_factor": expected_shape_factor,
                "pure_expansion_velocity_error_m_per_s": expansion_error,
                "free_subset_linear_momentum_error_kg_m_per_s": free_momentum_error,
                "free_subset_angular_momentum_error_kg_m2_per_s": free_angular_error,
                "degenerate_free_subset_velocity_error_m_per_s": degenerate_error},
            "finite_volume_compliance": {
                "initial_J": j_before, "after_first_solve_J": j_first,
                "after_same_substep_repeat_J": j_repeat,
                "first_multiplier": lambda_first, "repeat_multiplier": lambda_repeat,
                "after_deliberate_extra_multiplier_reset_J": j_with_deliberate_reset,
                "new_substep_resets_multiplier": True},
            "cotton_air_coefficient_sum_kg_per_m": actual_air_sum,
            "complete_simulation_step_finite": True,
            "limitations": ["Synthetic kernel verification; not real-material calibration.",
                            "Robot grasp and full wrapping behavior require the separate task regression."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check_runtime()
    encoded = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n")
    print(encoded)


if __name__ == "__main__":
    main()
