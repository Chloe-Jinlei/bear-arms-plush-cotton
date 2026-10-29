import sys,os,json,tomllib,time
from pathlib import Path
sweeps=int(sys.argv[1]);ram=Path('/run/user/1000/bear-material-task')/f'membrane-{sweeps}'
ram.mkdir(exist_ok=True)
for k,s in [('GS_CACHE_FILE_PATH','genesis'),('XDG_CACHE_HOME','cache'),('MPLCONFIGDIR','matplotlib'),('NUMBA_CACHE_DIR','numba')]:os.environ[k]=str(ram/s)
os.environ['QD_NUM_THREADS']='2';os.environ['PYTHONDONTWRITEBYTECODE']='1'
sys.path.insert(0,'/run/user/1000/bear-material-task/membrane-sweep-source')
import numpy as np
import genesis as gs
import trimesh
from pbd_adapter import existing_pbd_mesh
from cotton_bending import install_cotton_bending
from cotton_membrane import install_cotton_membrane
from material_response import install_material_response
root=Path('/home/chloe/.codex/.chatgpt-projects/g-p-6aa7fe6a24ac819183441af90be8f1e2/bear_arms_scene')
config=tomllib.loads((root/'config.toml').read_text());bcfg=config['bear'];ccfg=config['cloth'];sim=config['simulation']
a=np.load(root/'assets/cotton.npz');cp=a['points'].copy();faces=a['faces'];cp[:,1]+=-.65-cp[:,1].mean();cp[:,2]+=1.2-cp[:,2].mean()
bp=np.array([[.8,.8,.8],[.81,.8,.8],[.8,.81,.8],[.8,.8,.81]]);tet=np.array([[0,1,2,3]])
trimesh.Trimesh(vertices=bp,faces=np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3]]),process=False).export(ram/'body.obj')
cm=trimesh.Trimesh(vertices=cp,faces=faces,process=False);cm.export(ram/'cloth.obj')
gs.init(backend=gs.cpu,logging_level='warning',seed=7)
scene=gs.Scene(sim_options=gs.options.SimOptions(dt=.01,substeps=10),pbd_options=gs.options.PBDOptions(particle_size=sim['particle_size'],hash_grid_res=tuple(sim['hash_grid_size']),max_stretch_solver_iterations=sim['stretch_iterations'],max_bending_solver_iterations=sim['bending_iterations'],max_volume_solver_iterations=sim['volume_iterations'],lower_bound=(-1.2,-1.2,0),upper_bound=(1.2,1.,2.2)),vis_options=gs.options.VisOptions(n_support_neighbors=4),show_viewer=False)
with existing_pbd_mesh('bear',bp,tet,.001):bear=scene.add_entity(material=gs.materials.PBD.Elastic(),morph=gs.morphs.Mesh(file=str(ram/'body.obj'),file_meshes_are_zup=True,decimate=False,convexify=False))
with existing_pbd_mesh('cloth',cp,faces,ccfg['areal_density']*cm.area):cloth=scene.add_entity(material=gs.materials.PBD.Cloth(rho=ccfg['areal_density'],stretch_compliance=ccfg['stretch_compliance'],bending_compliance=ccfg['bending_compliance'],static_friction=ccfg['friction'],kinetic_friction=ccfg.get('kinetic_friction',ccfg['friction'])),morph=gs.morphs.Mesh(file=str(ram/'cloth.obj'),file_meshes_are_zup=True,decimate=False,convexify=False))
b=install_cotton_bending(scene,cloth,cp,faces,ccfg['bending_rigidity_nm'])
m=install_material_response(scene,bear,cloth,bp,tet,cp,faces,bcfg,ccfg,bending=b)
mem=install_cotton_membrane(scene,cloth,cp,faces,iterations=sweeps)
scene.build();m.configure();bear.fix_particles(particles_idx_local=np.arange(4),zero_velocity=True)
pins=np.array([np.argmin(np.linalg.norm(cp-[x,cp[:,1].min(),1.2],axis=1)) for x in (cp[:,0].min(),cp[:,0].max())]);cloth.fix_particles(particles_idx_local=pins,zero_velocity=True)
trace=[];start=time.perf_counter()
for step in range(250):
 scene.step();p=cloth.get_particles_pos().cpu().numpy();v=cloth.get_particles_vel().cpu().numpy();assert np.isfinite(p).all() and np.isfinite(v).all()
 d=mem.measure(p);d['step']=step+1;d['rms_speed']=float(np.sqrt((v*v).sum(1).mean()));d['anchor_drift']=float(np.linalg.norm(p[pins]-cp[pins],axis=1).max());trace.append(d)
 if step%50==49:print(sweeps,step+1,d['maximum_extension_fraction'],d['p95_absolute_edge_strain'],flush=True)
report={'sweeps':sweeps,'duration_s':2.5,'max_extension':max(t['maximum_extension_fraction'] for t in trace),'peak_p95_abs_strain':max(t['p95_absolute_edge_strain'] for t in trace),'max_anchor_drift':max(t['anchor_drift'] for t in trace),'final':trace[-1],'wall_seconds':time.perf_counter()-start,'membrane':mem.description,'trace':trace}
(ram/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ('trace','membrane')},indent=2),flush=True);gs.destroy()
