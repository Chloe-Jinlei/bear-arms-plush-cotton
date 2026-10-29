"""Small, reproducible checks of the cotton finite-extension constraint.

Run with the Genesis interpreter. ``--cache-dir`` can select a memory filesystem
when the system disk is full; ``--output`` optionally writes the result as JSON.
This checks one four-particle cloth, not the dressing task or full drape behavior.
"""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cotton_membrane import edge_constraints, install_cotton_membrane


def run(cache_root):
    for key, child in (("GS_CACHE_FILE_PATH", "genesis"), ("XDG_CACHE_HOME", "cache"),
                       ("MPLCONFIGDIR", "matplotlib"), ("NUMBA_CACHE_DIR", "numba")):
        os.environ.setdefault(key, str(cache_root / child))
    os.environ.setdefault("QD_NUM_THREADS", "2")
    import genesis as gs
    import trimesh
    from pbd_adapter import existing_pbd_mesh

    points = np.array([[0., 0., .1], [.01, 0., .1], [.01, .01, .1], [0., .01, .1]])
    faces = np.array([[0, 1, 2], [0, 2, 3]])
    edges, rest, maximum, directions, bounds = edge_constraints(points, faces)
    for begin, end in zip(bounds[:-1], bounds[1:]):
        assert len(np.unique(edges[begin:end])) == 2 * (end - begin)
    assert np.array_equal(np.bincount(directions), [2, 2, 1])
    assert np.allclose((maximum / rest)[directions < 2], 1.02)
    assert np.allclose((maximum / rest)[directions == 2], 1.10)
    _, scaled_rest, scaled_maximum, _, _ = edge_constraints(3 * points, faces)
    assert np.allclose(scaled_rest, 3 * rest)
    assert np.allclose(scaled_maximum, 3 * maximum)
    mesh_file = cache_root / "four_particle_cloth.obj"
    trimesh.Trimesh(vertices=points, faces=faces, process=False).export(mesh_file)
    gs.init(backend=gs.cpu, logging_level="warning", seed=7)
    try:
        scene = gs.Scene(
            sim_options=gs.options.SimOptions(dt=.001, substeps=1, gravity=(0, 0, 0)),
            pbd_options=gs.options.PBDOptions(particle_size=.001, hash_grid_res=(.1, .1, .1)),
            vis_options=gs.options.VisOptions(n_support_neighbors=4), show_viewer=False)
        with existing_pbd_mesh("cloth", points, faces, .000018):
            cloth = scene.add_entity(material=gs.materials.PBD.Cloth(),
                morph=gs.morphs.Mesh(file=str(mesh_file), file_meshes_are_zup=True,
                                     decimate=False, convexify=False))
        # Four sweeps suffice for this isolated patch. The full scene uses 24
        # because a long, corner-supported yarn network converges more slowly.
        membrane = install_cotton_membrane(scene, cloth, points, faces, iterations=4)
        scene.build()
        initial = points.copy()
        initial[:, 0] *= 1.3
        initial[:, 1] *= 1.2
        cloth.set_particles_pos(initial)
        before = membrane.measure()
        membrane.enforce()
        projected = cloth.get_particles_pos().cpu().numpy()
        after = membrane.measure(projected)
        mass = cloth.solver.particles_info.mass.to_numpy()
        center_error = float(np.linalg.norm(np.sum((projected - initial) * mass[:, None], axis=0) / mass.sum()))
        assert center_error < 1e-8
        assert after["maximum_extension_fraction"] < before["maximum_extension_fraction"]
        assert after["maximum_bound_excess_fraction"] < .001

        # The *current* cloth can rotate/translate freely: extension depends on
        # material edge lengths, not any preferred world-space cloth pose.
        rotation, _ = np.linalg.qr(np.random.default_rng(11).normal(size=(3, 3)))
        if np.linalg.det(rotation) < 0:
            rotation[:, 0] *= -1
        translation = np.array([.11, -.09, .17])
        moved_initial = initial @ rotation.T + translation
        cloth.set_particles_pos(moved_initial)
        membrane.enforce()
        moved_projected = cloth.get_particles_pos().cpu().numpy()
        expected = projected @ rotation.T + translation
        rigid_transform_error = float(np.abs(moved_projected - expected).max())
        assert rigid_transform_error < 1e-7

        compressed = points.copy()
        compressed[:, :2] *= .5
        cloth.set_particles_pos(compressed)
        membrane.enforce()
        compression_error = float(np.abs(cloth.get_particles_pos().cpu().numpy() - compressed).max())
        assert compression_error < 1e-8

        cloth.set_particles_pos(initial)
        cloth.fix_particles(particles_idx_local=np.array([0]), zero_velocity=True)
        membrane.enforce()
        anchored = cloth.get_particles_pos().cpu().numpy()
        anchor_error = float(np.linalg.norm(anchored[0] - initial[0]))
        assert anchor_error < 1e-8
        assert np.isfinite(anchored).all()
        return {
            "passed": True,
            "scope": "four-particle CPU kernel checks; full-scene strain limits are finite-iteration targets",
            "colors_disjoint": True,
            "direction_counts": [2, 2, 1],
            "uniform_scale_limits_covariant": True,
            "initial": before,
            "after": after,
            "mass_center_error_m": center_error,
            "rigid_transform_projection_error_m": rigid_transform_error,
            "compression_position_error_m": compression_error,
            "fixed_node_error_m": anchor_error,
            "description": membrane.description,
        }
    finally:
        gs.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, help="Directory for small test assets and compilation caches")
    parser.add_argument("--output", type=Path, help="Optional JSON result path")
    args = parser.parse_args()
    if args.cache_dir:
        args.cache_dir.mkdir(parents=True, exist_ok=True)
        result = run(args.cache_dir)
    else:
        with tempfile.TemporaryDirectory(prefix="cotton-membrane-check-") as temp:
            result = run(Path(temp))
    content = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + "\n")
    print(content)


if __name__ == "__main__":
    main()
