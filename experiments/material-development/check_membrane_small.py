import os,sys,json
from pathlib import Path
root=Path('/home/chloe/.codex/.chatgpt-projects/g-p-6aa7fe6a24ac819183441af90be8f1e2/bear_arms_scene')
sys.path.insert(0,str(root))
ram=Path('/run/user/1000/bear-material-task/membrane-small');ram.mkdir(exist_ok=True)
for k,s in [('GS_CACHE_FILE_PATH','genesis'),('XDG_CACHE_HOME','cache'),('MPLCONFIGDIR','matplotlib'),('NUMBA_CACHE_DIR','numba')]:os.environ[k]=str(ram/s)
os.environ['QD_NUM_THREADS']='2'
import numpy as np
import genesis as gs
import trimesh
from pbd_adapter import existing_pbd_mesh
from cotton_membrane import install_cotton_membrane,edge_constraints
p=np.array([[0.,0.,.1],[.01,0.,.1],[.01,.01,.1],[0.,.01,.1]])
f=np.array([[0,1,2],[0,2,3]])
e,l,m,d,b=edge_constraints(p,f)
for a,z in zip(b[:-1],b[1:]):assert len(np.unique(e[a:z]))==2*(z-a)
assert np.array_equal(np.bincount(d),[2,2,1])
mesh=trimesh.Trimesh(vertices=p,faces=f,process=False);path=ram/'small.obj';mesh.export(path)
gs.init(backend=gs.cpu,logging_level='warning')
scene=gs.Scene(sim_options=gs.options.SimOptions(dt=.001,substeps=1,gravity=(0,0,0)),pbd_options=gs.options.PBDOptions(particle_size=.001,hash_grid_res=(.1,.1,.1)),vis_options=gs.options.VisOptions(n_support_neighbors=4),show_viewer=False)
with existing_pbd_mesh('cloth',p,f,.000018):cloth=scene.add_entity(material=gs.materials.PBD.Cloth(),morph=gs.morphs.Mesh(file=str(path),file_meshes_are_zup=True,decimate=False,convexify=False))
mem=install_cotton_membrane(scene,cloth,p,f)
scene.build()
p0=p.copy();p0[:,0]*=1.3;p0[:,1]*=1.2
cloth.set_particles_pos(p0);before=mem.measure();mem.enforce();p1=cloth.get_particles_pos().cpu().numpy();after=mem.measure(p1)
mass=scene.sim.pbd_solver.particles_info.mass.to_numpy()
center_error=np.linalg.norm(((p1-p0)*mass[:,None]).sum(0)/mass.sum())
assert center_error<1e-8
assert after['maximum_extension_fraction']<before['maximum_extension_fraction']
assert after['maximum_bound_excess_fraction']<.001
compressed=p.copy();compressed[:,:2]*=.5
cloth.set_particles_pos(compressed);mem.enforce();unchanged=cloth.get_particles_pos().cpu().numpy();assert np.allclose(unchanged,compressed,atol=1e-8)
cloth.set_particles_pos(p0);cloth.fix_particles(particles_idx_local=np.array([0]),zero_velocity=True)
mem.enforce();anchored=cloth.get_particles_pos().cpu().numpy();assert np.allclose(anchored[0],p0[0],atol=1e-8)
report={'passed':True,'colors_disjoint':True,'direction_counts':[2,2,1],'initial':before,'after':after,'mass_center_error_m':float(center_error),'compressed_positions_unchanged':True,'fixed_node_unchanged':True,'description':mem.description}
(ram/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
gs.destroy()
