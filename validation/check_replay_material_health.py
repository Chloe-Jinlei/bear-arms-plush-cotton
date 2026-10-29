"""Read-only numerical-health audit of every saved replay video-frame state.

This reads replay-frames.npz once, then evaluates one frame at a time. The report
contains extrema and anomaly-frame indices/times, not a giant per-frame table.
All J values use source-asset rest tetrahedra, not a settled checkpoint. Cloth
extension targets are reported with residuals and do not act as hard fail limits.
Video-frame sampling cannot exclude between-frame/substep events and provides no
continuous-collision guarantee. The archive does not contain particle velocities.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import tomllib
import numpy as np


def audit(run, source):
    archive_path = run / 'replay-frames.npz'
    run_report = json.loads((run / 'report.json').read_text()) if (run / 'report.json').exists() else {}
    config = tomllib.loads((source / 'config.toml').read_text())
    with np.load(source / 'assets/bear.npz', allow_pickle=False) as data:
        rest_body = data['points'].astype(np.float64)
        tetra = data['tetra'].astype(np.int64)
    with np.load(source / 'assets/cotton.npz', allow_pickle=False) as data:
        rest_cloth = data['points'].astype(np.float64)
        faces = data['faces'].astype(np.int64)
    with np.load(archive_path, allow_pickle=False) as archive:
        arrays = {key: archive[key] for key in archive.files}
    required = ('time_s', 'phase', 'bear_positions', 'cloth_positions')
    if not all(key in arrays for key in required):
        raise ValueError('Replay archive is missing required time/phase/particle-position arrays')
    times, phases = arrays['time_s'], arrays['phase']
    n_frames = len(times)
    if n_frames == 0 or times.shape != (n_frames,) or phases.shape != (n_frames,):
        raise ValueError('Replay needs a nonempty one-dimensional timestamp and phase array')
    if arrays['bear_positions'].shape != (n_frames, len(rest_body), 3):
        raise ValueError('Bear replay shape differs from the source mesh')
    if arrays['cloth_positions'].shape != (n_frames, len(rest_cloth), 3):
        raise ValueError('Cloth replay shape differs from the source mesh')
    invalid_by_array = {}
    for key, value in arrays.items():
        if value.dtype.kind not in 'fci':
            continue
        if value.ndim == 0 or value.shape[0] != n_frames:
            raise ValueError(f'Unexpected non-frame-aligned numeric replay array: {key}')
        finite = np.isfinite(value).reshape(n_frames, -1).all(axis=1)
        invalid = np.flatnonzero(~finite).tolist()
        if invalid:
            invalid_by_array[key] = invalid
    invalid_frame_set = set(i for indices in invalid_by_array.values() for i in indices)
    fixed = np.flatnonzero(rest_body[:, 2] <= rest_body[:, 2].min() + config['bear']['fixed_band_height'])
    reference = rest_body + np.array([*config['bear']['position_xy'],
        config['table']['height'] + config['bear']['base_clearance']])
    rest_volume = np.linalg.det(rest_body[tetra[:, 1:]] - rest_body[tetra[:, :1]]) / 6
    if np.any(np.abs(rest_volume) <= 1e-14):
        raise ValueError('Source tetrahedra include a degenerate rest volume')
    edges = np.unique(np.sort(np.concatenate([
        faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1), axis=0)
    rest_delta = rest_cloth[edges[:, 1]] - rest_cloth[edges[:, 0]]
    rest_length = np.linalg.norm(rest_delta, axis=1)
    if np.any(rest_length <= 1e-12):
        raise ValueError('Source cloth has a collapsed edge')
    directions = np.full(len(edges), 2, dtype=np.int32)
    directions[np.abs(rest_delta[:, 1]) <= 1e-6 * rest_length] = 0
    directions[np.abs(rest_delta[:, 0]) <= 1e-6 * rest_length] = 1
    target = np.array([config['cloth'].get('warp_max_extension', .02),
                       config['cloth'].get('weft_max_extension', .02),
                       config['cloth'].get('bias_max_extension', .10)])

    def stamp(index):
        time = float(times[index])
        return {'frame_index': int(index), 'time_s': time if np.isfinite(time) else None,
                'phase': str(phases[index])}

    def events(indices):
        return {'count': len(indices), 'frame_indices': list(map(int, indices)),
                'times_s': [float(times[i]) if np.isfinite(times[i]) else None for i in indices]}

    min_j = max_drift = max_strain = max_p95 = max_target_excess = None
    directional_peaks = {name: None for name in ('warp', 'weft', 'bias')}
    inverted_frames, inversion_counts, inverted_tetrahedra = [], [], set()
    base_drift_frames, edge_ratio_over_1_3_frames = [], []
    target_excess_frames, near_floor_frames, analyzed = 0, 0, 0
    for index in range(n_frames):
        if index in invalid_frame_set:
            continue
        p = arrays['bear_positions'][index].astype(np.float64)
        q = arrays['cloth_positions'][index].astype(np.float64)
        volume = np.linalg.det(p[tetra[:, 1:]] - p[tetra[:, :1]]) / 6
        j = volume / rest_volume
        inverted = np.flatnonzero(j <= 0)
        if len(inverted):
            inverted_frames.append(index)
            inversion_counts.append(len(inverted))
            inverted_tetrahedra.update(map(int, inverted))
        if np.min(j) < config['bear'].get('minimum_volume_ratio', .1):
            near_floor_frames += 1
        location = int(np.argmin(j))
        if min_j is None or float(j[location]) < min_j['value']:
            min_j = {**stamp(index), 'value': float(j[location]), 'tetrahedron_index': location}
        drift = np.linalg.norm(p[fixed] - reference[fixed], axis=1)
        location = int(np.argmax(drift))
        if max_drift is None or float(drift[location]) > max_drift['value_m']:
            max_drift = {**stamp(index), 'value_m': float(drift[location]), 'node_index': int(fixed[location])}
        if float(drift.max()) > 1e-6:
            base_drift_frames.append(index)
        strain = np.linalg.norm(q[edges[:, 1]] - q[edges[:, 0]], axis=1) / rest_length - 1
        location = int(np.argmax(strain))
        if max_strain is None or float(strain[location]) > max_strain['strain_fraction']:
            max_strain = {**stamp(index), 'strain_fraction': float(strain[location]),
                          'length_ratio': float(strain[location] + 1), 'edge_nodes': edges[location].tolist()}
        p95 = float(np.percentile(np.maximum(strain, 0), 95))
        if max_p95 is None or p95 > max_p95['strain_fraction']:
            max_p95 = {**stamp(index), 'strain_fraction': p95}
        excess = np.maximum(strain - target[directions], 0)
        location = int(np.argmax(excess))
        if max_target_excess is None or float(excess[location]) > max_target_excess['fraction']:
            max_target_excess = {**stamp(index), 'fraction': float(excess[location]),
                                'edge_nodes': edges[location].tolist()}
        if np.max(excess) > 1e-6:
            target_excess_frames += 1
        if np.max(strain) > .3:
            edge_ratio_over_1_3_frames.append(index)
        for direction, name in enumerate(('warp', 'weft', 'bias')):
            selected = np.flatnonzero(directions == direction)
            if len(selected) == 0:
                continue
            location = int(selected[np.argmax(strain[selected])])
            value = float(strain[location])
            if directional_peaks[name] is None or value > directional_peaks[name]['strain_fraction']:
                directional_peaks[name] = {**stamp(index), 'strain_fraction': value,
                    'target_fraction': float(target[direction]), 'edge_nodes': edges[location].tolist()}
        analyzed += 1
    finite_times = np.isfinite(times).all()
    decreasing_times = np.flatnonzero(np.diff(times) < 0).tolist() if finite_times else []
    checks = {'all_numeric_frame_arrays_finite': not invalid_by_array,
              'all_frames_analyzed': analyzed == n_frames,
              'timestamps_nondecreasing': bool(finite_times and not decreasing_times),
              'no_sampled_bear_tetrahedron_inversions': not inverted_frames,
              'fixed_base_within_1um_at_every_sampled_frame': not base_drift_frames}
    inversion_event_summary = events(inverted_frames)
    inversion_event_summary.update({'inverted_tetrahedron_count_per_event_frame': list(map(int, inversion_counts)),
        'tetrahedron_frame_instances': int(sum(inversion_counts)),
        'maximum_simultaneously_inverted_tetrahedra': int(max(inversion_counts, default=0)),
        'unique_inverted_tetrahedron_indices': sorted(inverted_tetrahedra)})
    timestep = np.diff(times.astype(np.float64)) if finite_times else np.array([])
    return {'audit_status': 'passed' if all(checks.values()) else 'failed',
            'run_status': run_report.get('status'), 'run': str(run), 'source': str(source),
            'archive': str(archive_path), 'frame_count': n_frames, 'analyzed_frame_count': analyzed,
            'time_range_s': [float(times[0]), float(times[-1])] if finite_times else None,
            'sample_spacing_s_min_median_max': [float(timestep.min()), float(np.median(timestep)), float(timestep.max())]
                if len(timestep) else None,
            'checks': checks,
            'nonfinite_frames_by_array': {key: events(indices) for key, indices in invalid_by_array.items()},
            'minimum_bear_J': min_j, 'inversion_events': inversion_event_summary,
            'frames_below_volume_floor_target': near_floor_frames,
            'maximum_fixed_base_drift': max_drift, 'base_drift_over_1um_events': events(base_drift_frames),
            'maximum_cloth_edge_tensile_strain': max_strain,
            'maximum_frame_p95_cloth_tensile_strain': max_p95,
            'cloth_directional_strain_peaks': directional_peaks,
            'maximum_cloth_extension_target_excess': max_target_excess,
            'frames_with_cloth_target_excess_over_1e_6': target_excess_frames,
            'cloth_edge_ratio_over_1_3_events': events(edge_ratio_over_1_3_frames),
            'source_sha256': {name: hashlib.sha256((source/name).read_bytes()).hexdigest()
                for name in ('config.toml', 'assets/bear.npz', 'assets/cotton.npz')},
            'limitations': ['Every archived video-frame state is checked; unsaved intervals and simulation substeps are not covered.',
                'No continuous-collision or nonpenetration guarantee is inferred from positive tetrahedron volumes.',
                'Replay contains positions/joint coordinates, not particle velocities or force histories.',
                'Cloth target excess and samples above the existing 1.3 edge-ratio diagnostic are reported independently; finite target residuals do not alone fail this health audit.',
                'Original rest tetrahedra are used; the initial checkpoint is already settled and is not the volume reference.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--source', type=Path, help='Defaults to RUN/source-at-run')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.run, args.source or args.run / 'source-at-run')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: result[key] for key in (
        'audit_status', 'run_status', 'frame_count', 'analyzed_frame_count', 'time_range_s',
        'checks', 'minimum_bear_J', 'maximum_fixed_base_drift', 'maximum_cloth_edge_tensile_strain',
        'maximum_frame_p95_cloth_tensile_strain')}, indent=2, allow_nan=False))
    return 0 if result['audit_status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
