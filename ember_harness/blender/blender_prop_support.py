"""Shared original-prop construction and export in dedicated Blender processes."""
import json
import bpy
from mathutils import Vector
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from design import validate as validate_design, color


class PropScene:
    def __init__(self, collection_name, asset_id):
        if not bpy.app.background:
            raise ValueError('Use a dedicated Blender --background process; do not reset an artist scene')
        bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
        bpy.context.scene.unit_settings.system='METRIC'; bpy.context.scene.unit_settings.scale_length=1
        self.collection=bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(self.collection)
        self.root=self.empty('AssetRoot',(0,0,0))
        self.root['asset_id']=asset_id; self.root['units']='metres'
        self.design=None
        if '--design' in sys.argv:
            self.design=validate_design(json.loads(Path(sys.argv[sys.argv.index('--design')+1]).read_text(encoding='utf-8')))

    def empty(self, name, location, parent=None):
        obj=bpy.data.objects.new(name,None); self.collection.objects.link(obj)
        obj.location=location; obj.parent=parent
        return obj

    def material(self, name, color, metal=0, rough=.5):
        if self.design and name!='MAT_Collision' and not name.startswith('Studio'):
            from design import color as rgb
            index=1 if 'Brass' in name else 2 if 'Seal' in name else 0
            color=rgb(self.design['palette'][index])
            if 'Slat' in name: color=tuple(min(1,c*1.25) for c in color)
            if 'Iron' in name: color=tuple(c*.28 for c in color)
            metal=self.design['metallic'] if 'Brass' in name or 'Iron' in name else metal
            rough=self.design['roughness']
        mat=bpy.data.materials.new(name); mat.use_nodes=True
        bsdf=mat.node_tree.nodes.get('Principled BSDF'); bsdf.inputs['Base Color'].default_value=(*color,1)
        bsdf.inputs['Metallic'].default_value=metal; bsdf.inputs['Roughness'].default_value=rough
        return mat

    def box(self, name, dim, location, mat, parent=None, bevel=.012):
        if self.design and bevel==.012: bevel=self.design['bevel']
        if self.design and name in ('SM_BodyBand','SM_LidBand'):
            dim=(self.design['band_width'],*dim[1:])
        if self.design and name=='SM_LeafBand': dim=(*dim[:2],self.design['band_width'])
        bpy.ops.mesh.primitive_cube_add(size=1,location=location)
        obj=bpy.context.object; obj.name=name; obj.dimensions=dim
        for collection in list(obj.users_collection): collection.objects.unlink(obj)
        self.collection.objects.link(obj)
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        obj.data.materials.append(mat)
        if bevel:
            modifier=obj.modifiers.new('Soft manufactured edges','BEVEL'); modifier.width=bevel; modifier.segments=2
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        world=obj.matrix_world.copy(); obj.parent=parent if parent is not None else self.root; obj.matrix_world=world
        return obj

    def finish(self, output, spec):
        self.root['art_direction']=spec['art_direction']
        if self.design:
            self.root['production_design']=json.dumps(self.design,sort_keys=True)
            (output/'production-design.json').write_text(json.dumps(self.design,indent=2),encoding='utf-8')
        bpy.context.view_layer.update()
        points=[obj.matrix_world @ Vector(corner) for obj in self.collection.objects
            if obj.type=='MESH' and not obj.name.startswith('COLLISION_') for corner in obj.bound_box]
        low=[min(p[i] for p in points) for i in range(3)]; high=[max(p[i] for p in points) for i in range(3)]
        print('BLENDER_DIMENSIONS_METRES',json.dumps([high[0]-low[0],high[2]-low[2],high[1]-low[1]]))
        (output/'asset-spec.json').write_text(json.dumps(spec,indent=2),encoding='utf-8')
        for obj in bpy.context.scene.objects: obj.select_set(obj.name in self.collection.objects)
        bpy.ops.wm.save_as_mainfile(filepath=str(output/(spec['id']+'.blend')))
        bpy.ops.export_scene.gltf(filepath=str(output/(spec['id']+'.glb')),export_format='GLB',
            use_selection=True,export_yup=True,export_extras=True,export_animations=False,export_cameras=False,
            export_lights=False,export_texcoords=False,export_normals=True,export_materials='EXPORT')
        print('EXPORTED_PROP',spec['id'],output.name)
        if '--renders' in sys.argv: self.render(output,spec)

    def render(self,output,spec):
        scene=bpy.context.scene
        scene.render.engine='CYCLES';scene.cycles.samples=12;scene.cycles.use_denoising=True
        scene.render.resolution_x=512;scene.render.resolution_y=512;scene.render.resolution_percentage=100
        scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
        scene.world.color=(.18,.18,.18)
        height=spec['dimensions_m'][1]
        bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.012))
        plane=bpy.context.object;plane.name='StudioGround'
        plane.data.materials.append(self.material('StudioGround',(.09,.10,.12),0,.8))
        for location,power,size in [((2,-3,4),450,4),((-3,-1,2),220,3),((0,3,4),600,3)]:
            bpy.ops.object.light_add(type='AREA',location=location)
            lamp=bpy.context.object;lamp.data.energy=power;lamp.data.shape='DISK';lamp.data.size=size
            lamp.rotation_euler=(Vector((0,0,height/2))-lamp.location).to_track_quat('-Z','Y').to_euler()
        bpy.ops.object.camera_add(location=(2.7,-3.8,height+1.6))
        camera=bpy.context.object;camera.data.type='ORTHO';camera.data.ortho_scale=max(spec['dimensions_m'])*1.85
        camera.rotation_euler=(Vector((0,0,height*.48))-camera.location).to_track_quat('-Z','Y').to_euler();scene.camera=camera
        scene.render.filepath=str(output/'hero.png');bpy.ops.render.render(write_still=True)
        hinge=bpy.data.objects.get('GateHinge') or bpy.data.objects.get('LidPivot')
        axis=2 if 'GateHinge' in bpy.data.objects else 0
        hinge.rotation_euler[axis]=1.35 if axis==2 else -1.35
        scene.render.filepath=str(output/'impact.png');bpy.ops.render.render(write_still=True)
        hinge.rotation_euler[axis]=0
        bpy.ops.wm.save_as_mainfile(filepath=str(output/(spec['id']+'.blend')))
