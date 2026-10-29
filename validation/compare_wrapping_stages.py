from pathlib import Path
import argparse,json,hashlib
import numpy as np

def compare(new, old, source):
 b=np.load(source/'assets/bear.npz');c=np.load(source/'assets/cotton.npz')
 bp=b['points'].astype(float);t=b['tetra'];cp=c['points'].astype(float);f=c['faces']
 e=np.unique(np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1),axis=0)
 d=cp[e[:,1]]-cp[e[:,0]];l=np.linalg.norm(d,axis=1);directions=np.full(len(e),2);directions[np.abs(d[:,1])<1e-6*l]=0;directions[np.abs(d[:,0])<1e-6*l]=1
 v0=np.linalg.det(bp[t[:,1:]]-bp[t[:,:1]])/6
 dm=np.stack([cp[f[:,1],:2]-cp[f[:,0],:2],cp[f[:,2],:2]-cp[f[:,0],:2]],axis=-1);inv=np.linalg.inv(dm)
 def metrics(path):
  with np.load(path,allow_pickle=False) as a:
   p=a['bear_positions'].astype(float);q=a['cloth_positions'].astype(float);meta=json.loads(str(a['metadata']))
   assert p.shape==bp.shape and q.shape==cp.shape
   strain=np.linalg.norm(q[e[:,1]]-q[e[:,0]],axis=1)/l-1
   j=np.linalg.det(p[t[:,1:]]-p[t[:,:1]])/6/v0
   ds=np.stack([q[f[:,1]]-q[f[:,0]],q[f[:,2]]-q[f[:,0]]],axis=-1)
   sv=np.linalg.svd(ds@inv,compute_uv=False)
   return {'phase':meta['phase'],'step':meta['step'],'cloth_edge_tensile_max':float(strain.max()),'cloth_edge_tensile_p95':float(np.percentile(np.maximum(strain,0),95)),'cloth_edge_abs_strain_p95':float(np.percentile(np.abs(strain),95)),
    'cloth_by_direction':{name:{'maximum':float(strain[directions==i].max()),'p95_tensile':float(np.percentile(np.maximum(strain[directions==i],0),95))}for i,name in enumerate(('warp','weft','bias'))},
    'cloth_principal_stretch_max':float(sv[:,0].max()),'cloth_principal_stretch_p95':float(np.percentile(sv[:,0],95)),
    'bear_volume_ratio':float(np.sum(np.abs(v0)*j)/np.abs(v0).sum()),'bear_minimum_J':float(j.min()),'bear_inverted_tets':int((j<=0).sum()),'finite':bool(np.isfinite(p).all() and np.isfinite(q).all())}
 newreport=json.loads((new/'report.json').read_text());oldreport=json.loads((old/'report.json').read_text())
 files=sorted(p.name for p in new.glob('state-*.npz') if (old/p.name).exists())
 rows=[]
 for name in files:
  n,o=metrics(new/name),metrics(old/name)
  rows.append({'state':name,'new':n,'original':o,'delta_max_edge_strain':n['cloth_edge_tensile_max']-o['cloth_edge_tensile_max'],'delta_p95_edge_tensile_strain':n['cloth_edge_tensile_p95']-o['cloth_edge_tensile_p95']})
 rows.sort(key=lambda x:x['new']['step'])
 shnew=newreport.get('source_sha256',{});shold=oldreport.get('source_sha256',{})
 return {'new_run_status':newreport.get('status'),'original_run_status':oldreport.get('status'),'matching_stage_count':len(rows),
  'asset_sha256_common_entries_equal':all(shnew[k]==shold[k] for k in set(shnew)&set(shold)),
  'common_asset_hash_entries':sorted(set(shnew)&set(shold)),
  'method':'Matched checkpoint phase names, original mesh edges/triangles/tetrahedra; tensile strain is length/rest_length-1; bear J uses original rest tetrahedra, not settled initial checkpoint. Different adaptive timing is not time-aligned.',
  'stages':rows}
if __name__=='__main__':
 p=argparse.ArgumentParser(description='Compare matched phase checkpoints, not matched simulation times.')
 p.add_argument('--new',type=Path,required=True)
 p.add_argument('--original',type=Path,required=True)
 p.add_argument('--source',type=Path,help='Defaults to NEW/source-at-run')
 p.add_argument('--output',type=Path,required=True)
 a=p.parse_args()
 r=compare(a.new,a.original,a.source or a.new/'source-at-run')
 a.output.parent.mkdir(parents=True,exist_ok=True)
 a.output.write_text(json.dumps(r,indent=2)+'\n')
 print('status',r['new_run_status'],r['original_run_status'],'asset_hash_match',r['asset_sha256_common_entries_equal'])
 print('stage | new/orig max-edge% | new/orig p95% | new warp/weft/bias max% | old warp/weft/bias max% | new/orig Vratio | new/orig minJ | inverted new/orig')
 for x in r['stages']:
  n,o=x['new'],x['original'];nd='/'.join(f'{100*n["cloth_by_direction"][k]["maximum"]:.2f}'for k in ('warp','weft','bias'));od='/'.join(f'{100*o["cloth_by_direction"][k]["maximum"]:.2f}'for k in ('warp','weft','bias'))
  print(f'{n["phase"]:20} {100*n["cloth_edge_tensile_max"]:6.2f}/{100*o["cloth_edge_tensile_max"]:6.2f} {100*n["cloth_edge_tensile_p95"]:5.2f}/{100*o["cloth_edge_tensile_p95"]:5.2f} {nd:18} {od:18} {n["bear_volume_ratio"]:.5f}/{o["bear_volume_ratio"]:.5f} {n["bear_minimum_J"]:.3f}/{o["bear_minimum_J"]:.3f} {n["bear_inverted_tets"]}/{o["bear_inverted_tets"]}')
