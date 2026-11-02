"""Original hinged gate; run Blender --background --python THIS -- --output NEW_DIR."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from blender_prop_support import PropScene

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--fixed-collider',action='store_true',help='Generate the deliberately invalid fixed proxy rehearsal')
parser.add_argument('--design',type=Path)
parser.add_argument('--renders',action='store_true')
parser.add_argument('--art-direction',default=None)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output.mkdir(parents=True,exist_ok=False)
production=PropScene('COL_CourierWaygate','courier-waygate')
root=production.root;box=production.box;material=production.material
hinge=production.empty('GateHinge',(-.58,0,.06),root)
production.empty('Socket_Latch',(.38,-.35,1.03),root)
wood=material('MAT_TealOak',(.035,.19,.16),0,.62)
slat=material('MAT_TealSlats',(.055,.28,.22),0,.58)
brass=material('MAT_AgedBrass',(.58,.32,.095),.75,.32)
iron=material('MAT_DarkIron',(.045,.055,.055),.72,.44)
seal=material('MAT_AmberSeal',(1,.43,.07),.15,.25)
helper=material('MAT_Collision',(.9,.1,.1))
for x in [-.67,.67]:
    box('SM_StonePost',(.16,.30,2.02),(x,0,1.01),iron,bevel=.025)
    for z in [.16,1.98]:box('SM_PostBand',(.175,.31,.08),(x,0,z),brass,bevel=.009)
box('SM_Lintel',(1.5,.30,.18),(0,0,2.11),wood,bevel=.02)
box('SM_LintelInlay',(.88,.025,.055),(0,-.151,2.12),brass,bevel=.009)
box('SM_GateLeaf',(1.16,.10,1.94),(0,0,1.03),wood,hinge)
count=production.design['slats'] if production.design else 5
for x in [-.46+.92*i/(count-1) for i in range(count)]:box('SM_LeafSlat',(.205,.025,1.78),(x,-.055,1.03),slat,hinge,bevel=.006)
for z in [.22,1.84]:box('SM_LeafBand',(1.14,.04,.075),(0,-.074,z),brass,hinge,bevel=.008)
for z in [.30,1.75]:box('SM_HingePlate',(.14,.055,.15),(-.52,-.068,z),iron,hinge)
box('SM_LatchPlate',(.11,.045,.22),(.40,-.084,1.03),brass,hinge)
box('SM_LatchGrip',(.075,.05,.12),(.40,-.135,1.03),seal,hinge,bevel=.014)
padding=production.design['collision_padding'] if production.design else 0
proxy=box('COLLISION_Gate',(1.16+padding*2,.10+padding*2,1.94),(0,0,1.03),helper,root if args.fixed_collider else hinge,bevel=0)
proxy.hide_render=True;proxy.display_type='WIRE';proxy['role']='collision_proxy'
for name,x in [('COLLISION_PostLeft',-.67),('COLLISION_PostRight',.67)]:
    post=box(name,(.16,.30,2.02),(x,0,1.01),helper,root,bevel=0)
    post.hide_render=True;post.display_type='WIRE';post['role']='collision_proxy'
spec=dict(profile='hinged-prop-v1',id='courier-waygate',display_name='Courier waygate',
    dimensions_m=[1.5,2.2,.31],dimension_tolerance_m=.02,
    required_nodes=['AssetRoot','GateHinge','COLLISION_Gate','Socket_Latch','COLLISION_PostLeft','COLLISION_PostRight'],
    art_direction='Original courier waygate: teal oak, aged brass bands, dark posts, amber latch, readable at gameplay distance.',
    interaction=dict(pivot_node='GateHinge',axis='y',open_angle_rad=1.8,collision_node='COLLISION_Gate',
        socket_node='Socket_Latch',noun='gate',success_text='Passage open',passage=True,
        static_collision_nodes=['COLLISION_PostLeft','COLLISION_PostRight']))
if args.art_direction: spec['art_direction']=args.art_direction
production.finish(args.output,spec)
