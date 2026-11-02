"""Pure bounded design data, shared by the host and standalone Blender scripts."""
import math
import re

DEFAULT = dict(palette=['#2D7566','#A97A35','#FF9A40'], slats=5, band_width=.065,
               bevel=.012, metallic=.75, roughness=.58, collision_padding=.02)
RANGES = dict(band_width=(.04,.075), bevel=(.004,.018), metallic=(.2,.9),
              roughness=(.25,.8), collision_padding=(0,.5))


def validate(settings):
    if not isinstance(settings,dict) or set(settings)!=set(DEFAULT):
        raise ValueError('Supply only the bounded prop design fields')
    palette=settings['palette']
    if not isinstance(palette,list) or len(palette)!=3 or any(not isinstance(c,str) or not re.fullmatch('#[0-9a-fA-F]{6}',c) for c in palette):
        raise ValueError('Choose three original palette colors')
    if type(settings['slats']) is not int or settings['slats'] not in (3,5,7):
        raise ValueError('Choose three, five or seven slats')
    for key,(low,high) in RANGES.items():
        value=settings[key]
        if type(value) not in (float,int) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError('Design parameter outside its approved range: '+key)
    return settings


def color(value):
    def linear(v): return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
    return tuple(linear(int(value[i:i+2],16)/255) for i in (1,3,5))
