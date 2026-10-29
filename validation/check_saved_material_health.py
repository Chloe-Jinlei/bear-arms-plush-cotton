"""Read-only health audit of saved wrapping checkpoints; never imports Genesis.

Checks every state*.npz, including checkpoint-history, against unchanged source
assets. Yarn/bias limits are reported as targets with finite convergence residual,
not hard pass/fail thresholds. Checkpoint-only results cannot exclude transients
between saved states. Run after the full task ends (or use --allow-partial for an
explicitly incomplete snapshot of currently available checkpoints).
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import tomllib
import numpy as np


def audit(run, source, allow_partial=False):
    report = json.loads((run / 'report.json').read_text())
    status = report.get('status', 'unknown')
    partial = status not in {'passed', 'failed'}
    if partial and not allow_partial:
        raise RuntimeError('The wrapping run is still in progress; defer the final audit or use --allow-partial')
    config = tomllib.loads((source / 'config.toml').read_text())
    b = np.load(source / 'assets/bear.npz', allow_pickle=False)
    c = np.load(source / 'assets/cotton.npz', allow_pickle=False)
    bp = b['points'].astype(np.float64)
    tetra = b['tetra'].astype(np.int64)
    cp = c['points'].astype(np.float64)
    faces = c['faces'].astype(np.int64)
    reference = bp + np.array([*config['bear']['position_xy'],
        config['table']['height'] + config['bear']['base_clearance']])
    fixed = np.flatnonzero(bp[:, 2] <= bp[:, 2].min() + config['bear']['fixed_band_height'])
    recorded_fixed = np.asarray(report['simulation']['fixed_particle_indices'])
    if not np.array_equal(fixed, recorded_fixed):
        raise ValueError('Reported fixed-base indices do not match the source config and mesh')
    rest_vol = np.linalg.det(bp[tetra[:, 1:]] - bp[tetra[:, :1]]) / 6
    edges = np.unique(np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1), axis=0)
    rest_delta = cp[edges[:, 1]] - cp[edges[:, 0]]
    rest_length = np.linalg.norm(rest_delta, axis=1)
    directions = np.full(len(edges), 2, dtype=np.int32)
    directions[np.abs(rest_delta[:, 1]) <= 1e-6 * rest_length] = 0
    directions[np.abs(rest_delta[:, 0]) <= 1e-6 * rest_length] = 1
    targets = np.array([config['cloth']['warp_max_extension'], config['cloth']['weft_max_extension'],
                        config['cloth']['bias_max_extension']])
    dm = np.stack([cp[faces[:, 1], :2] - cp[faces[:, 0], :2],
                   cp[faces[:, 2], :2] - cp[faces[:, 0], :2]], axis=-1)
    inverse_dm = np.linalg.inv(dm)
    records, errors = [], []
    nonfinite, total_inversions, collapsed, bad_fixed = 0, 0, 0, 0
    minimum_j, maximum_drift, maximum_edge, maximum_principal = None, None, None, None
    directional_peaks = {name: None for name in ('warp', 'weft', 'bias')}
    state_paths = sorted(run.rglob('state*.npz'))
    if not state_paths:
        raise ValueError('No saved state checkpoints found')
    for path in state_paths:
        label = str(path.relative_to(run))
        try:
            with np.load(path, allow_pickle=False) as data:
                bad_arrays = [key for key in data.files if data[key].dtype.kind in 'fci'
                              and not np.isfinite(data[key]).all()]
                if bad_arrays:
                    nonfinite += 1
                    errors.append({'file': label, 'nonfinite_arrays': bad_arrays})
                    continue
                p = data['bear_positions'].astype(np.float64)
                q = data['cloth_positions'].astype(np.float64)
                if p.shape != bp.shape or q.shape != cp.shape:
                    raise ValueError('Particle position shape does not match source assets')
                metadata = json.loads(str(data['metadata'])) if 'metadata' in data else {}
                node_flags = data['bear_free_flags'].ravel() if 'bear_free_flags' in data else None
                if node_flags is not None and np.any(node_flags[fixed]):
                    bad_fixed += 1
                volume = np.linalg.det(p[tetra[:, 1:]] - p[tetra[:, :1]]) / 6
                j = volume / rest_vol
                inverted = int(np.count_nonzero(j <= 0))
                total_inversions += inverted
                drift = np.linalg.norm(p[fixed] - reference[fixed], axis=1)
                length = np.linalg.norm(q[edges[:, 1]] - q[edges[:, 0]], axis=1)
                strain = length / rest_length - 1
                excess = np.maximum(strain - targets[directions], 0)
                ds = np.stack([q[faces[:, 1]] - q[faces[:, 0]], q[faces[:, 2]] - q[faces[:, 0]]], axis=-1)
                principal = np.linalg.svd(ds @ inverse_dm, compute_uv=False)
                area = np.linalg.norm(np.cross(ds[:, :, 0], ds[:, :, 1]), axis=1) / 2
                count_collapsed = int(np.count_nonzero(area < 1e-12))
                collapsed += count_collapsed
                local_peaks = {}
                for direction, name in enumerate(('warp', 'weft', 'bias')):
                    selected = np.flatnonzero(directions == direction)
                    local_index = int(selected[np.argmax(strain[selected])])
                    peak = float(strain[local_index])
                    local_peaks[name] = peak
                    if directional_peaks[name] is None or peak > directional_peaks[name]['strain_fraction']:
                        directional_peaks[name] = {'file': label, 'strain_fraction': peak,
                            'target_fraction': float(targets[direction]), 'edge_nodes': edges[local_index].tolist(),
                            'target_excess_fraction': float(max(0, peak - targets[direction]))}
                row = {'file': label, 'phase': metadata.get('phase'), 'step': metadata.get('step'),
                    'finite': True, 'bear_inverted_tetrahedra': inverted,
                    'bear_minimum_J': float(j.min()), 'bear_J_percentiles_1_50_99': np.percentile(j, [1, 50, 99]).tolist(),
                    'bear_volume_ratio': float(np.sum(np.abs(rest_vol) * j) / np.abs(rest_vol).sum()),
                    'bear_maximum_base_drift_m': float(drift.max()),
                    'bear_base_free_flag_count': int(np.count_nonzero(node_flags[fixed])) if node_flags is not None else None,
                    'cloth_maximum_edge_tensile_strain_fraction': float(strain.max()),
                    'cloth_p99_edge_tensile_strain_fraction': float(np.percentile(strain, 99)),
                    'cloth_peak_strain_by_direction': local_peaks,
                    'cloth_maximum_target_excess_fraction': float(excess.max()),
                    'cloth_maximum_principal_stretch': float(principal[:, 0].max()),
                    'cloth_minimum_triangle_area_m2': float(area.min()), 'cloth_collapsed_triangles': count_collapsed}
                for name, key in (('bear', 'bear_velocities'), ('cloth', 'cloth_velocities')):
                    if key in data:
                        velocity = data[key].astype(np.float64)
                        row[name + '_rms_speed_m_per_s'] = float(np.sqrt(np.mean(np.sum(velocity**2, axis=1))))
                        row[name + '_maximum_speed_m_per_s'] = float(np.linalg.norm(velocity, axis=1).max())
                records.append(row)
                if minimum_j is None or row['bear_minimum_J'] < minimum_j['value']:
                    minimum_j = {'file': label, 'value': row['bear_minimum_J'], 'tetrahedron_index': int(np.argmin(j))}
                if maximum_drift is None or row['bear_maximum_base_drift_m'] > maximum_drift['value_m']:
                    maximum_drift = {'file': label, 'value_m': row['bear_maximum_base_drift_m'],
                                     'node_index': int(fixed[np.argmax(drift)])}
                if maximum_edge is None or row['cloth_maximum_edge_tensile_strain_fraction'] > maximum_edge['fraction']:
                    maximum_edge = {'file': label, 'fraction': row['cloth_maximum_edge_tensile_strain_fraction'],
                                    'edge_nodes': edges[int(np.argmax(strain))].tolist()}
                if maximum_principal is None or row['cloth_maximum_principal_stretch'] > maximum_principal['ratio']:
                    maximum_principal = {'file': label, 'ratio': row['cloth_maximum_principal_stretch'],
                                         'triangle_index': int(np.argmax(principal[:, 0]))}
        except Exception as error:
            errors.append({'file': label, 'read_or_analysis_error': str(error)})
    checks = {'all_checkpoints_read': len(records) == len(state_paths),
              'all_saved_numeric_arrays_finite': nonfinite == 0,
              'no_saved_bear_tetrahedron_inversions': total_inversions == 0,
              'fixed_base_position_within_1um': maximum_drift is not None and maximum_drift['value_m'] <= 1e-6,
              'base_flags_remain_fixed': bad_fixed == 0,
              'no_saved_cloth_triangles_below_1e_12_m2': collapsed == 0}
    return {'audit_status': 'passed' if all(checks.values()) else 'failed', 'run_status': status,
            'run_complete_and_passed': status == 'passed', 'partial_audit': partial,
            'checks': checks, 'checkpoint_files_found': len(state_paths),
            'checkpoints_analyzed': len(records), 'nonfinite_checkpoint_count': nonfinite,
            'summed_inverted_tetrahedra_across_checkpoints': total_inversions,
            'minimum_bear_J': minimum_j, 'maximum_fixed_base_drift': maximum_drift,
            'maximum_cloth_edge_tensile_strain': maximum_edge,
            'maximum_cloth_principal_stretch': maximum_principal,
            'directional_strain_peaks': directional_peaks,
            'source_sha256': {name: hashlib.sha256((source/name).read_bytes()).hexdigest()
                              for name in ('config.toml', 'scene.py', 'material_response.py', 'cotton_bending.py', 'cotton_membrane.py')},
            'errors': errors, 'checkpoints': records,
            'limitations': ['This audit samples saved state*.npz files, including checkpoint-history; it cannot exclude between-checkpoint events.',
                            'Warp/weft/bias extension targets permit finite-solve residuals; excess is reported, not treated as a failure by itself.',
                            'This is a numerical-health audit, not experimental material calibration or a replacement for the full task checks.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--source', type=Path, help='Defaults to RUN/source-at-run')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args()
    source = args.source or args.run / 'source-at-run'
    result = audit(args.run, source, args.allow_partial)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    compact = {k: v for k, v in result.items() if k not in ('source_sha256', 'checkpoints', 'errors', 'limitations')}
    print(json.dumps(compact, indent=2, allow_nan=False))
    if result['errors']:
        print(json.dumps(result['errors'], indent=2))
    return 0 if result['audit_status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
