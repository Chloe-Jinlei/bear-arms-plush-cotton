"""Scene-local material response for the preserved Genesis 1.4.3 meshes.

This adapter changes constitutive response, never assets, particle targets, or
robot control.  The tetrahedral volume constraint is normalized by rest volume;
its compliance follows U = K V0 (J - 1)^2 / 2.  It replaces the legacy volume
projection, whose mass weights include an extra squared-gradient factor.

References:
  Macklin et al., XPBD (2016), equations 5, 17 and 18:
  https://matthias-research.github.io/pages/publications/XPBD.pdf
"""

from importlib.metadata import version

import numpy as np


def _unique_edges(elements):
    elements = np.asarray(elements, dtype=np.int32)
    return np.unique(np.sort(np.concatenate([
        elements[:, [i, j]] for i in range(elements.shape[1])
        for j in range(i + 1, elements.shape[1])]), axis=1), axis=0)


def _boundary_edges(tetra):
    faces = np.sort(np.concatenate([
        tetra[:, [0, 1, 2]], tetra[:, [0, 1, 3]],
        tetra[:, [0, 2, 3]], tetra[:, [1, 2, 3]]]), axis=1)
    faces, counts = np.unique(faces, axis=0, return_counts=True)
    return {tuple(edge) for edge in _unique_edges(faces[counts == 1])}


def _edge_colors(edges, n_particles):
    """Greedy disjoint-edge colors, allowing dissipative in-place impulses."""
    used = [set() for _ in range(n_particles)]
    groups = []
    for index, (a, b) in enumerate(edges):
        unavailable = used[a] | used[b]
        color = 0
        while color in unavailable:
            color += 1
        if color == len(groups):
            groups.append([])
        groups[color].append(index)
        used[a].add(color)
        used[b].add(color)
    order = np.asarray([i for group in groups for i in group], dtype=np.int32)
    bounds = np.cumsum([0] + [len(group) for group in groups]).tolist()
    return order, bounds


def install_material_response(scene, bear, cloth, bear_points, bear_tetra,
                              cloth_points, cloth_faces, bcfg, ccfg,
                              bending=None):
    """Install before build/contact adapters; call ``configure`` after build.

    ``bending`` may expose ``reset()``; its XPBD multipliers are then reset at
    precisely the same substep boundary as the volumetric multipliers.  Volume
    re-solves requested by surface contact retain their accumulated multipliers.
    This scene's existing contact and attachment adapters support one environment;
    this adapter makes that same restriction explicit.
    """
    import genesis as gs
    import quadrants as qd
    import torch

    if version("genesis-world") != "1.4.3" or scene.is_built:
        raise RuntimeError("Install the Genesis 1.4.3 material adapter before build")
    if bear.solver is not cloth.solver:
        raise ValueError("Bear and cloth must share the PBD solver")
    solver = bear.solver

    bulk_compression = float(bcfg.get("bulk_modulus_compression_pa", 3000.0))
    bulk_expansion = float(bcfg.get("bulk_modulus_expansion_pa", 15000.0))
    bulk_relaxation = float(bcfg.get("bulk_relaxation", 1.0))
    minimum_j = float(bcfg.get("minimum_volume_ratio", 0.10))
    max_volume_correction = float(bcfg.get("maximum_volume_correction_m", 0.001))
    interior_compliance = float(bcfg.get("internal_stretch_compliance", 0.003))
    surface_compliance = float(bcfg.get("surface_stretch_compliance", 0.001))
    bear_damping = float(bcfg.get("internal_damping_per_s", 40.0))
    cloth_damping = float(ccfg.get("internal_damping_per_s", 4.0))
    air_density = float(ccfg.get("air_density_kg_m3", 1.225))
    drag_coefficient = float(ccfg.get("air_drag_coefficient", 1.0))
    values = [bulk_compression, bulk_expansion, bulk_relaxation, minimum_j,
              max_volume_correction, interior_compliance, surface_compliance,
              bear_damping, cloth_damping, air_density, drag_coefficient]
    if not np.all(np.isfinite(values)) or min(values) < 0:
        raise ValueError("Material settings must be finite and nonnegative")
    if min(bulk_compression, bulk_expansion, max_volume_correction) <= 0:
        raise ValueError("Bulk moduli and correction limit must be positive")
    if not 0 < bulk_relaxation <= 1 or not 0 < minimum_j < 1:
        raise ValueError("bulk_relaxation must be in (0,1], minimum_volume_ratio in (0,1)")

    # The importer normalizes tet orientation without changing connectivity.
    tet_local = np.asarray(bear._elems, dtype=np.int32)
    input_tet = np.asarray(bear_tetra, dtype=np.int32)
    if not np.array_equal(np.sort(tet_local, axis=1), np.sort(input_tet, axis=1)):
        raise ValueError("Material adapter requires the supplied bear topology")
    body_points = np.asarray(bear_points, dtype=np.float64)
    cloth_points = np.asarray(cloth_points, dtype=np.float64)
    cloth_faces = np.asarray(cloth_faces, dtype=np.int32)
    rest_volume = np.linalg.det(
        body_points[tet_local[:, 1:]] - body_points[tet_local[:, :1]]) / 6.0
    if np.any(rest_volume <= 1e-14):
        raise ValueError("Material adapter requires positive, nondegenerate tetrahedra")
    incidence = np.bincount(tet_local.ravel(), minlength=len(body_points))
    # One factor for the whole constraint preserves equal/opposite internal
    # corrections. Multipliers receive the very same factor as positions.
    tet_relaxation = bulk_relaxation / incidence[tet_local].max(axis=1)
    tet_global = tet_local + bear.particle_start

    body_edges = np.asarray(bear._edges, dtype=np.int32)
    cloth_edges = _unique_edges(cloth_faces)
    surface_edges = _boundary_edges(tet_local)
    edge_compliance = np.asarray([
        surface_compliance if tuple(edge) in surface_edges else interior_compliance
        for edge in body_edges], dtype=np.float32)
    edges = np.concatenate([body_edges + bear.particle_start,
                            cloth_edges + cloth.particle_start])
    body_degree = max(1, int(np.bincount(body_edges.ravel()).max()))
    cloth_degree = max(1, int(np.bincount(cloth_edges.ravel()).max()))
    # Degree normalization bounds accumulated damping as connectivity changes.
    # Coloring, rather than a simultaneous velocity sum, guarantees that each
    # individual operation removes kinetic energy from the free system.
    rates = np.concatenate([
        np.full(len(body_edges), bear_damping / body_degree),
        np.full(len(cloth_edges), cloth_damping / cloth_degree)]).astype(np.float32)
    order, color_bounds = _edge_colors(edges, solver.n_particles)
    edges, rates = edges[order], rates[order]
    face_area = np.linalg.norm(np.cross(
        cloth_points[cloth_faces[:, 1]] - cloth_points[cloth_faces[:, 0]],
        cloth_points[cloth_faces[:, 2]] - cloth_points[cloth_faces[:, 0]]), axis=1) / 2.0
    particle_area = np.zeros(len(cloth_points), dtype=np.float64)
    np.add.at(particle_area, cloth_faces.ravel(), np.repeat(face_area / 3.0, 3))
    # Genesis's drag is F = c_i |v_i| v_i. Scale c_i by represented area,
    # otherwise refining the very same fabric increases its total air drag.
    air_coefficients = (0.5 * air_density * drag_coefficient * particle_area).astype(np.float32)

    def tensor(values, integer=False):
        return torch.as_tensor(np.ascontiguousarray(values), device=gs.device,
                               dtype=gs.tc_int if integer else gs.tc_float)

    @qd.data_oriented
    class MaterialResponse:
        def __init__(self):
            self.solver, self.bending = solver, bending
            self.native_store_initial = solver._kernel_store_initial_pos
            self.native_volume = solver._kernel_solve_volume
            self.tetra = tensor(tet_global, True)
            self.rest_volume = tensor(rest_volume)
            self.tet_relaxation = tensor(tet_relaxation)
            self.edges, self.rates = tensor(edges, True), tensor(rates)
            self.edge_compliance = tensor(edge_compliance)
            self.air_coefficients = tensor(air_coefficients)
            self.color_bounds = color_bounds
            self.n_colors = len(color_bounds) - 1
            self.n_tetra = len(tet_local)
            self.n_body = len(body_points)
            self.n_cloth = len(cloth_points)
            self.body_start, self.cloth_start = bear.particle_start, cloth.particle_start
            self.body_edge_start = bear._edge_start
            self.n_body_edges = len(body_edges)
            self.lambda_bulk = qd.field(dtype=gs.qd_float, shape=(self.n_tetra, 1))
            self.lambda_floor = qd.field(dtype=gs.qd_float, shape=(self.n_tetra, 1))
            self.delta = qd.Vector.field(3, dtype=gs.qd_float, shape=(self.n_body, 1))
            self.configured = False
            self.description = {
                "model": "compressible tetrahedral filling with an existing stronger surface edge network",
                "volume_constraint": "J = signed current tetrahedron volume / rest volume; C = J - 1",
                "compression_bulk_modulus_pa": bulk_compression,
                "expansion_bulk_modulus_pa": bulk_expansion,
                "volume_compliance": "1 / (bulk_modulus_pa * rest_volume_m3), inverse joules for C=J-1",
                "xpbd_accumulated_multipliers": True,
                "multiplier_reset": "once per substep, retained across contact volume re-solves",
                "jacobi_constraint_relaxation": "bulk_relaxation / maximum incident tetrahedra at the four nodes",
                "bulk_relaxation": bulk_relaxation,
                "minimum_signed_volume_ratio": minimum_j,
                "maximum_constraint_particle_correction_m": max_volume_correction,
                "bear_edge_stretch_compliance_m_per_N": {
                    "interior": interior_compliance, "surface": surface_compliance},
                "internal_damping": {
                    "model": "degree-normalized axial relative-velocity impulses on disjoint edge colors",
                    "bear_rate_per_s": bear_damping, "cloth_rate_per_s": cloth_damping,
                    "bear_maximum_degree": body_degree, "cloth_maximum_degree": cloth_degree,
                    "colors": self.n_colors,
                    "rigid_translation_and_rotation_preserved": True,
                    "fixed_and_link_attached_velocities_unchanged": True},
                "cotton_air_drag": {
                    "model": "isotropic quadratic particle drag weighted by barycentric rest area",
                    "air_density_kg_per_m3": air_density, "drag_coefficient": drag_coefficient,
                    "total_represented_area_m2": float(particle_area.sum()),
                    "coefficient_min_max_kg_per_m": [float(air_coefficients.min()), float(air_coefficients.max())],
                    "orientation_resolved_aerodynamics": False},
                "native_stretch_solver_retained": True,
                "real_material_measurements_calibrated": False,
                "geometry_assets_controls_and_installed_genesis_unchanged": True,
            }

        def configure(self):
            """Set per-edge/per-particle properties after native build uploads."""
            if not scene.is_built or self.solver._B != 1:
                raise RuntimeError("Configure the material adapter after building a single environment")
            if self.solver._n_elems != self.n_tetra:
                raise RuntimeError("This scene-local adapter expects the bear to be the sole tetrahedral entity")
            self.configure_properties(self.edge_compliance, self.air_coefficients)
            self.reset()
            self.configured = True

        def store_initial(self, f):
            if not self.configured:
                # Genesis builds solver fields, marks the scene built, then
                # performs a compilation step before scene.build() returns.
                # Properties must already apply to that step; configure() is
                # also safe to call explicitly again after the build returns.
                self.configure()
            self.native_store_initial(f)
            self.reset()
            if self.bending is not None:
                self.bending.reset()
            self.damp_edges(self.edges, self.rates)

        @qd.kernel
        def configure_properties(self, compliance: qd.types.ndarray(), air: qd.types.ndarray()):
            for i in range(self.n_body_edges):
                self.solver.edges_info[self.body_edge_start + i].stretch_compliance = compliance[i]
            for i in range(self.n_cloth):
                self.solver.particles_info[self.cloth_start + i].air_resistance = air[i]

        @qd.kernel
        def reset(self):
            for i in range(self.n_tetra):
                self.lambda_bulk[i, 0] = 0.0
                self.lambda_floor[i, 0] = 0.0

        @qd.kernel
        def damp_edges(self, pairs: qd.types.ndarray(), rates: qd.types.ndarray()):
            for color in qd.static(range(self.n_colors)):
                for edge in range(self.color_bounds[color], self.color_bounds[color + 1]):
                    a, b = pairs[edge, 0], pairs[edge, 1]
                    wa = self.solver.particles[a, 0].free / self.solver.particles_info[a].mass
                    wb = self.solver.particles[b, 0].free / self.solver.particles_info[b].mass
                    direction = self.solver.particles[a, 0].pos - self.solver.particles[b, 0].pos
                    length = direction.norm()
                    if wa + wb > 0.0 and length > 1e-12:
                        direction /= length
                        relative_speed = (self.solver.particles[a, 0].vel
                                          - self.solver.particles[b, 0].vel).dot(direction)
                        fraction = 1.0 - qd.exp(-rates[edge] * self.solver._substep_dt)
                        impulse = -fraction * relative_speed / (wa + wb) * direction
                        self.solver.particles[a, 0].vel += wa * impulse
                        self.solver.particles[b, 0].vel -= wb * impulse

        def solve_volume(self, f):
            self.volume_kernel(self.tetra, self.rest_volume, self.tet_relaxation)

        @qd.kernel
        def volume_kernel(self, tetra: qd.types.ndarray(), v0: qd.types.ndarray(),
                          relaxation: qd.types.ndarray()):
            for iteration in qd.static(range(solver._max_volume_solver_iterations)):
                for i in range(self.n_body):
                    self.delta[i, 0] = qd.Vector.zero(gs.qd_float, 3)
                for el in range(self.n_tetra):
                    ids = qd.Vector([tetra[el, 0], tetra[el, 1], tetra[el, 2], tetra[el, 3]])
                    p1 = self.solver.particles[ids[0], 0].pos
                    p2 = self.solver.particles[ids[1], 0].pos
                    p3 = self.solver.particles[ids[2], 0].pos
                    p4 = self.solver.particles[ids[3], 0].pos
                    rest = v0[el]
                    j = (p2 - p1).dot((p3 - p1).cross(p4 - p1)) / (6.0 * rest)
                    gradients = qd.Matrix.rows([
                        (p4 - p2).cross(p3 - p2) / (6.0 * rest),
                        (p3 - p1).cross(p4 - p1) / (6.0 * rest),
                        (p4 - p1).cross(p2 - p1) / (6.0 * rest),
                        (p2 - p1).cross(p3 - p1) / (6.0 * rest)])
                    weights = qd.Vector.zero(gs.qd_float, 4)
                    denominator = gs.qd_float(0.0)
                    for k in qd.static(range(4)):
                        weights[k] = self.solver.particles[ids[k], 0].free / self.solver.particles_info[ids[k]].mass
                        denominator += weights[k] * gradients[k, :].norm_sqr()
                    if denominator > 1e-20:
                        modulus = bulk_compression
                        if j >= 1.0:
                            modulus = bulk_expansion
                        alpha = 1.0 / (modulus * rest * self.solver._substep_dt**2)
                        dl_bulk = -(j - 1.0 + alpha * self.lambda_bulk[el, 0]) / (denominator + alpha)
                        # Unilateral anti-inversion support, separate from the
                        # compliant filling's rest-volume energy.
                        dl_floor = qd.max(0.0, self.lambda_floor[el, 0]
                                         - (j - minimum_j) / denominator) - self.lambda_floor[el, 0]
                        dl_bulk *= relaxation[el]
                        dl_floor *= relaxation[el]
                        largest_delta = gs.qd_float(0.0)
                        for k in qd.static(range(4)):
                            largest_delta = qd.max(largest_delta, weights[k] * qd.abs(dl_bulk + dl_floor)
                                                   * gradients[k, :].norm())
                        correction_scale = qd.min(1.0, max_volume_correction / qd.max(largest_delta, 1e-20))
                        dl_bulk *= correction_scale
                        dl_floor *= correction_scale
                        self.lambda_bulk[el, 0] += dl_bulk
                        self.lambda_floor[el, 0] += dl_floor
                        for k in qd.static(range(4)):
                            self.delta[ids[k] - self.body_start, 0] += weights[k] * (dl_bulk + dl_floor) * gradients[k, :]
                for i in range(self.n_body):
                    self.solver.particles[self.body_start + i, 0].pos += self.delta[i, 0]

    adapter = MaterialResponse()
    solver._kernel_store_initial_pos = adapter.store_initial
    solver._kernel_solve_volume = adapter.solve_volume
    return adapter
