"""Run with Blender --background --python THIS -- --output DIR [--collision-padding .02]."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from blender_prop_support import PropScene

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--collision-padding', type=float, default=.02)
parser.add_argument('--design',type=Path)
parser.add_argument('--renders',action='store_true')
parser.add_argument('--art-direction',default=None)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
if not 0 <= args.collision_padding <= .5: raise ValueError('Collision padding must be 0–0.5 m')
args.output.mkdir(parents=True, exist_ok=False)
production=PropScene('COL_DeliveryChest','delivery-chest')
root=production.root
empty,material,box=production.empty,production.material,production.box
lid=empty('LidPivot',(0,.35,.62),root)
socket=empty('Socket_Delivery',(0,-.43,.64),root)
wood=material('MAT_TealOak',(.035,.19,.16),0,.62)
slat=material('MAT_TealSlats',(.055,.28,.22),0,.58)
brass=material('MAT_AgedBrass',(.58,.32,.095),.75,.32)
dark=material('MAT_DarkIron',(.045,.055,.055),.72,.44)
glow=material('MAT_AmberSeal',(1,.43,.07),.15,.25)
helper=material('MAT_Collision',(.9,.1,.1))
box('SM_ChestFloor',(1.16,.70,.07),(0,0,.135),wood)
for y in [-.3225,.3225]: box('SM_ChestWall',(1.16,.055,.45),(0,y,.395),wood)
for x in [-.5525,.5525]: box('SM_ChestSide',(.055,.59,.45),(x,0,.395),wood)
box('SM_InteriorLining',(1.04,.58,.025),(0,0,.1825),dark,bevel=.004)
box('SM_DeliveryParcel',(.38,.28,.16),(0,0,.28),glow,bevel=.02)
box('SM_ParcelRibbon',(.045,.29,.165),(0,0,.28),brass,bevel=.004)
box('SM_ChestLid',(1.2,.76,.18),(0,0,.71),wood,lid)
for x in [-.48,.48]:
    for y in [-.27,.27]: box('SM_Foot',(.18,.17,.10),(x,y,.05),dark)
count=production.design['slats'] if production.design else 5
for x in [-.46+.92*i/(count-1) for i in range(count)]:
    box('SM_FrontSlat',(.205,.025,.42),(x,-.354,.36),slat,bevel=.006)
    box('SM_LidSlat',(.205,.65,.018),(x,0,.795),slat,lid,bevel=.005)
for x in [-.49,.49]:
    box('SM_BodyBand',(.065,.724,.53),(x,0,.36),brass,bevel=.008)
    box('SM_LidBand',(.065,.768,.19),(x,0,.715),brass,lid,bevel=.008)
box('SM_LowerRail',(1.18,.73,.045),(0,0,.115),brass)
box('SM_LidLip',(1.2,.77,.025),(0,0,.625),dark,lid,bevel=.006)
box('SM_Latch',(.14,.06,.20),(0,-.393,.59),brass,lid,bevel=.015)
box('SM_AmberSeal',(.065,.015,.075),(0,-.428,.60),glow,lid,bevel=.009)
for x in [-.58,.58]: box('SM_CarryHandle',(.05,.25,.08),(x,0,.43),brass)
padding=production.design['collision_padding'] if production.design else args.collision_padding
collider=box('COLLISION_Chest',(1.2+padding*2,.76+padding*2,.8),(0,0,.4),helper,bevel=0)
collider.display_type='WIRE'; collider.hide_render=True; collider['role']='collision_proxy'
# Blender Z-up becomes glTF Y-up; dimensions below use glTF axes.
spec=dict(id='delivery-chest',dimensions_m=[1.21,.81,.821],dimension_tolerance_m=.02,
    required_nodes=['AssetRoot','LidPivot','COLLISION_Chest','Socket_Delivery'],
    art_direction='Original stylized courier chest: teal oak, aged brass, amber seal, softened edges, readable at 3 metres.')
if args.art_direction: spec['art_direction']=args.art_direction
production.finish(args.output,spec)
