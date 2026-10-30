"""Publication-grade scientific biological vector symbols in a 100 x 100 local coordinate system.

Crafted with realistic biological morphology, structural domains, volumetric multi-tone shading,
and pure flat SVG paths that export natively to SVG, PDF, high-DPI PNG, and PowerPoint DrawingML.
"""
from __future__ import annotations
import html
import math


def tint(color: str, amount: float = 0.8) -> str:
    color = color.lstrip('#')
    if len(color) == 3:
        color = ''.join(c * 2 for c in color)
    return '#' + ''.join(
        f'{round(int(color[i:i+2], 16) * (1 - amount) + 255 * amount):02x}'
        for i in (0, 2, 4)
    )


def shade(color: str, amount: float = 0.25) -> str:
    color = color.lstrip('#')
    if len(color) == 3:
        color = ''.join(c * 2 for c in color)
    return '#' + ''.join(
        f'{max(0, min(255, round(int(color[i:i+2], 16) * (1 - amount)))):02x}'
        for i in (0, 2, 4)
    )


def symbol(kind: str, color: str, state: str = '', stroke: str | None = None, stroke_scale: float = 1, lightness: float = 0.8) -> str:
    stroke = stroke or color
    light = tint(color, lightness)
    mid = tint(color, 0.55)
    dark = shade(color, 0.25)
    deep = shade(color, 0.45)
    p: list[str] = []

    def path(d: str, fill: str = 'none', line: str = stroke, sw: float = 1.2, **attrs):
        extra = ' '.join(f'{k.replace("_", "-")}="{html.escape(str(v), quote=True)}"' for k, v in attrs.items())
        p.append(f'<path d="{d}" fill="{fill}" stroke="{line}" stroke-width="{sw * stroke_scale:.3f}" stroke-linecap="round" stroke-linejoin="round" {extra}/>')

    def ellipse(cx: float, cy: float, rx: float, ry: float, fill: str = light, line: str = stroke, sw: float = 1.2, **attrs):
        extra = (" " + " ".join(f'{k.replace("_", "-")}="{html.escape(str(v), quote=True)}"' for k, v in attrs.items())) if attrs else ""
        p.append(f'<ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" fill="{fill}" stroke="{line}" stroke-width="{sw * stroke_scale:.3f}"{extra}/>')

    def circle(cx: float, cy: float, r: float, fill: str = light, line: str = stroke, sw: float = 1.2, **attrs):
        ellipse(cx, cy, r, r, fill, line, sw, **attrs)

    def rect(x: float, y: float, w: float, h: float, rx: float = 3, fill: str = light, line: str = stroke, sw: float = 1.2, **attrs):
        extra = (" " + " ".join(f'{k.replace("_", "-")}="{html.escape(str(v), quote=True)}"' for k, v in attrs.items())) if attrs else ""
        p.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="{rx:.2f}" fill="{fill}" stroke="{line}" stroke-width="{sw * stroke_scale:.3f}"{extra}/>')

    if kind in ('cell','stem_cell') and state.startswith('plant_'):
        phase=state[6:]
        p.append('<g data-cell-profile="plant">')
        rect(8,8,84,84,rx=4,fill=light,sw=2.4,data_feature='cell-wall')
        rect(12,12,76,76,rx=3,fill='none',line=tint(color,.3),sw=.7)
        def chromosome(x,y):
            path(f'M {x-3} {y-4} L {x+3} {y+4} M {x+3} {y-4} L {x-3} {y+4}',line='#BE185D',sw=2.1)
        if phase in ('interphase','prophase'):
            ellipse(50,50,23,22,fill=mid,sw=1.1,data_feature='intact-nuclear-envelope')
            if phase=='interphase':
                circle(44,44,4,fill=deep,line='none',sw=0)
                path('M 35 50 Q 43 42 55 51 T 64 48 M 38 59 Q 48 65 59 57',line=deep,sw=.9)
            else:
                for x,y in ((41,43),(57,43),(42,57),(58,57)):chromosome(x,y)
        elif phase in ('prometaphase','metaphase','anaphase'):
            p.append('<g data-feature="acentrosomal-spindle">')
            for yy in (30,43,57,70):
                path(f'M 19 50 Q 33 {yy} 48 {yy} M 81 50 Q 67 {yy} 52 {yy}',line='#279878',sw=.9)
            p.append('</g>')
            if phase=='metaphase':
                for yy in (30,43,57,70):chromosome(50,yy)
            elif phase=='prometaphase':
                for x,y in ((42,39),(58,46),(44,60),(61,65)):chromosome(x,y)
                path('M 32 31 L 38 28 M 62 28 L 68 32 M 31 66 L 37 70 M 64 69 L 69 64',sw=.8)
            else:
                for yy in (31,44,57,70):
                    path(f'M 37 {yy-4} L 31 {yy} L 37 {yy+4} M 63 {yy-4} L 69 {yy} L 63 {yy+4}',line='#BE185D',sw=2)
        elif phase in ('telophase','cytokinesis'):
            for xx in (30,70):
                ellipse(xx,50,13,15,fill=mid,sw=1)
                path(f'M {xx-7} 46 Q {xx} 41 {xx+7} 48 M {xx-5} 55 Q {xx} 60 {xx+6} 54',line=deep,sw=.8)
            if phase=='cytokinesis':
                path('M 50 10 V 90',line='#B37A38',sw=2.1,data_feature='cell-plate')
            else:
                path('M 50 34 V 66',line='#B37A38',sw=1.5,stroke_dasharray='3 2',data_feature='forming-cell-plate')
        else:ellipse(50,50,23,22,fill=mid,sw=1.1)
        p.append('</g>')
        return ''.join(p)
    if state.startswith('legend_') and state[7:] in ('activates','inhibits','binds','converts','transports','sequence','associates'):
        from relation_visuals import relation_parts
        p.append('<g transform="scale(4 10)">')
        for tag,attrs in relation_parts(state[7:],(1,5),(8,5),(4.5,5),stroke,1.05):
            p.append('<'+tag+' '+' '.join(f'{k}="{html.escape(str(v),quote=True)}"' for k,v in attrs.items())+'/>')
        p.append('</g>')
        return ''.join(p)
    if state in ('timeline_axis','timeline_vertical'):
        if state=='timeline_axis':
            path('M 5 50 H 95',sw=1.2)
            for x in (5,35,65,95):
                path(f'M {x} 20 V 80',sw=1.1);circle(x,50,3,fill=stroke,sw=0)
        else:
            path('M 50 5 V 95',sw=1.2)
            for y in (5,35,65,95):
                path(f'M 20 {y} H 80',sw=1.1);circle(50,y,3,fill=stroke,sw=0)
        return ''.join(p)
    if state.startswith('flow_'):
        shape=state[5:]
        if shape=='decision':path('M 50 2 L 98 50 L 50 98 L 2 50 Z',fill=light,sw=1.6)
        elif shape=='input':path('M 17 2 H 98 L 83 98 H 2 Z',fill=light,sw=1.6)
        elif shape=='document':path('M 2 2 H 98 V 82 Q 74 68 50 86 T 2 86 Z',fill=light,sw=1.6)
        elif shape=='database':
            path('M 2 15 C 2 -2 98 -2 98 15 V 85 C 98 102 2 102 2 85 Z',fill=light,sw=1.6)
            path('M 2 15 C 2 32 98 32 98 15',sw=1.4)
        elif shape=='terminal':rect(2,2,96,96,rx=46,fill=light,sw=1.6)
        elif shape=='lane':rect(0,0,100,100,rx=2,fill=tint(color,.975),line=tint(color,.75),sw=.5)
        elif shape=='badge':
            rect(2,2,96,96,rx=6,fill=light,sw=1.4)
            rect(2,2,22,96,rx=4,fill=tint(color,.25),line='none')
        elif shape=='capsule':
            rect(2,16,96,68,rx=34,fill=light,sw=1.6)
        elif shape=='milestone':
            rect(2,2,96,96,rx=5,fill=light,sw=1.5)
            rect(2,2,96,24,rx=3,fill=tint(color,.35),line='none')
        elif shape=='apparatus':
            rect(2,2,96,96,rx=6,fill=light,sw=1.4)
            path('M 78 8 H 88 M 80 8 V 22 C 80 28 86 28 86 22 V 8',sw=1.2,line=tint(color,.45),fill='none')
        elif shape=='comparison':
            rect(2,2,96,96,rx=6,fill=light,sw=1.4)
            rect(2,2,96,10,rx=2,fill=tint(color,.4),line='none')
        else:rect(2,2,96,96,rx=5,fill=light,sw=1.6)
        return ''.join(p)
    if state in ('contact_left','contact_right'):
        rect(0,0,100,100,rx=0,fill=tint(color,.95),line='none',sw=0)
        xx=96 if state=='contact_left' else 4
        path(f'M {xx} 0 Q {xx-5} 50 {xx} 100',line=tint(color,.25),sw=1.1)
        path(f'M {xx+3 if state=="contact_left" else xx-3} 0 Q {xx-2 if state=="contact_left" else xx-8} 50 {xx+3 if state=="contact_left" else xx-3} 100',line=tint(color,.45),sw=.65)
    elif state=='cell_context':
        path('M 8 31 C 12 8 37 2 63 7 C 90 9 99 34 94 61 C 91 89 67 99 39 93 C 13 89 0 61 8 31 Z',fill=tint(color,.96),line=tint(color,.35),sw=.8)
        path('M 10 32 C 14 11 37 5 63 10 C 87 12 96 35 91 61 C 88 86 66 96 40 90 C 16 86 3 61 10 32 Z',line=tint(color,.55),sw=.5)
    elif state == 'phagophore':
        path('M 73 15 C 1 0 1 100 73 85 L 69 77 C 17 88 17 12 69 23 Z',fill=light,sw=1.8)
        path('M 70 19 C 9 6 9 94 70 81',line=tint(color,.4),sw=1)
        ellipse(48,50,13,10,fill=mid)
    elif state in ('autophagosome','autolysosome','phagolysosome','endosome','lysosome','lnp','phagosome'):
        circle(50,50,44,fill=light,sw=1.7)
        circle(50,50,40,fill='none',line=tint(color,.4),sw=1)
        if state=='autophagosome':
            circle(50,50,34,fill='none',sw=1.5);circle(50,50,30,fill='none',sw=.8)
            ellipse(47,49,16,9,fill=mid)
        elif state=='lnp':
            for a in range(0,360,24):
                rad=math.radians(a);x,y=50+39*math.cos(rad),50+39*math.sin(rad)
                circle(x,y,2.1,fill=mid,sw=.6)
            path('M 25 40 Q 36 28 45 45 T 66 42 T 74 63 M 28 65 Q 42 52 52 65 T 72 63',line='#D18B52',sw=2)
        elif state in ('autolysosome','phagolysosome','lysosome'):
            for x,y,r in ((30,31,5),(65,32,4),(27,65,4),(62,64,6),(48,50,3)):
                circle(x,y,r,fill=tint('#C18668',.4),line='#B47B63',sw=.8)
            if state=='autolysosome':
                path('M 23 45 L 36 39 L 42 51 L 28 55 Z M 48 69 L 59 77 L 68 67 L 58 60 Z',fill=mid,sw=.9)
                path('M 35 24 Q 53 15 70 31 M 72 47 Q 81 62 71 77',line=tint(color,.5),sw=1)
        elif state=='phagosome':
            rect(27,37,44,23,rx=10,fill=mid);path('M 35 50 Q 43 40 50 52 T 63 47',sw=1)
    elif kind=='pathogen' and state=='bacterium':
        rect(13,26,73,46,rx=22,fill=light,sw=1.7)
        path('M 25 42 Q 34 30 43 46 T 62 47 T 77 42 M 85 50 Q 100 30 96 10',sw=1.3)
        for x,y in ((30,57),(54,59),(67,38)):circle(x,y,2.5,fill=mid,sw=.6)
    elif state=='organoid':
        for a in range(0,360,40):
            rad=math.radians(a);circle(50+28*math.cos(rad),50+28*math.sin(rad),14,fill=light,sw=1.4)
        circle(50,50,23,fill=tint(color,.95),sw=1)
    elif kind=='endothelial' and state in ('intact','disrupted'):
        for i in range(3):
            x=2+i*33;dy=10 if state=='disrupted' and i==1 else 0
            rect(x,27+dy,29,40,rx=4,fill=light);ellipse(x+14,47+dy,7,9,fill=mid)
        if state=='intact':
            path('M 32 28 V 66 M 65 28 V 66',line='#B98559',sw=2.3)
    elif kind == 'membrane':
        # Realistic phospholipid bilayer slab with polar spherical heads and curved acyl chains
        rect(0, 22, 100, 56, rx=2, fill=tint(color, 0.92), line='none', sw=0)
        rect(0, 44, 100, 12, rx=1, fill=tint(color, 0.85), line='none', sw=0)
        # Upper leaflet
        for x in (4, 11, 18, 25, 32, 39, 46, 53, 60, 67, 74, 81, 88, 95):
            path(f'M {x-1.5} 20 Q {x-3} 32 {x-1.2} 44 M {x+1.5} 20 Q {x+3} 32 {x+1.2} 44', line=tint(color, 0.4), sw=1.1)
            circle(x, 15, 4.2, fill=mid, line=stroke, sw=0.9)
            circle(x-1.1, 13.8, 1.2, fill='#ffffff', line='none', sw=0)
        # Lower leaflet
        for x in (4, 11, 18, 25, 32, 39, 46, 53, 60, 67, 74, 81, 88, 95):
            path(f'M {x-1.5} 80 Q {x-3} 68 {x-1.2} 56 M {x+1.5} 80 Q {x+3} 68 {x+1.2} 56', line=tint(color, 0.4), sw=1.1)
            circle(x, 85, 4.2, fill=mid, line=stroke, sw=0.9)
            circle(x-1.1, 83.8, 1.2, fill='#ffffff', line='none', sw=0)
        # Cholesterol steroid planar inserts
        for cx in (32, 67):
            rect(cx-1.8, 38, 3.6, 24, rx=1, fill='#e8c878', line='#a68638', sw=0.7)

    elif kind == 'nuclear_pore':
        # Octagonal nuclear pore complex spanning outer and inner nuclear membranes
        path('M 2 24 H 32 M 68 24 H 98 M 2 76 H 32 M 68 76 H 98', line=tint(color, 0.4), sw=3)
        rect(24, 10, 18, 80, rx=5, fill=light, line=stroke, sw=1.4)
        rect(58, 10, 18, 80, rx=5, fill=light, line=stroke, sw=1.4)
        # Central transporter plug
        circle(50, 50, 10, fill=mid, line=stroke, sw=1.2)
        # Cytoplasmic filaments and nuclear basket
        path('M 33 10 Q 20 2 12 1 M 67 10 Q 80 2 88 1 M 50 10 V 2', line=stroke, sw=1.5)
        path('M 33 90 Q 50 102 67 90', line=stroke, sw=1.4)

    elif kind == 'ligand':
        # Generic folded ligand; oligomeric state is specified by the scene.
        path('M 12 48 C 7 25 24 13 39 24 C 49 6 70 11 74 31 C 94 30 95 56 78 65 C 76 88 48 94 38 75 C 17 84 5 65 12 48 Z',fill=light)
        path('M 26 40 Q 35 32 42 38 M 57 62 Q 67 55 74 62',sw=1.2)

    elif kind in ('receptor', 'receptor_dimer'):
        # RTK / Cytokine receptor monomer or dimer with L1/CRD/L2 domains, transmembrane helix, and kinase domain
        offsets = [28, 62] if kind == 'receptor_dimer' else [45]
        for x in offsets:
            # Extracellular ligand binding domains (L1, CRD, L2)
            path(f'M {x-12} 8 C {x-26} 22 {x-18} 34 {x-7} 40 L {x-7} 66 L {x+7} 66 L {x+7} 40 C {x+22} 26 {x+14} 12 {x+6} 6 C {x-1} 14 {x-6} 14 {x-12} 8 Z', fill=light, line=stroke, sw=1.5)
            # Internal domain shading
            path(f'M {x-8} 14 C {x-18} 24 {x-12} 32 {x-4} 36 L {x-4} 45 L {x+4} 45 L {x+4} 36 C {x+15} 25 {x+9} 14 {x+3} 10 Z', fill=mid, line='none', sw=0)
            # Transmembrane alpha-helical segment traversing membrane
            rect(x-5, 48, 10, 22, rx=2, fill=tint(color, 0.65), line=stroke, sw=1.2)
            # Intracellular tyrosine kinase domain (N-lobe & C-lobe)
            ellipse(x, 82, 11, 8.5, fill=light, line=stroke, sw=1.4)
            ellipse(x, 90, 8.5, 6, fill=mid, line=stroke, sw=1.2)
        if kind == 'receptor_dimer':
            # Dimerization interface and trapped cytokine in binding pocket
            path('M 37 32 Q 45 38 53 32', line=tint(color, 0.3), sw=1.8)

    elif kind == 'gpcr':
        # 7-Transmembrane helix bundle with extracellular & intracellular loops
        for i in range(7):
            x = 11 + i * 11.5
            # Transmembrane alpha-helical cylinder
            rect(x, 24, 7.5, 52, rx=3, fill=light, line=stroke, sw=1.2)
            rect(x+1, 26, 2.5, 48, rx=1, fill='#ffffff', line='none', sw=0)
            # Connecting loops
            if i < 6:
                y_anchor = 24 if i % 2 == 0 else 76
                y_peak = 8 if i % 2 == 0 else 92
                path(f'M {x+7.5} {y_anchor} Q {x+13} {y_peak} {x+19} {y_anchor}', line=stroke, sw=1.6)

    elif kind == 'protein':
        path('M 12 30 C 19 10 43 9 54 22 C 74 10 93 29 87 48 C 101 68 81 88 63 82 C 47 98 23 91 22 77 C 3 73 0 48 12 30 Z',fill=light)
        path('M 53 22 Q 44 38 58 48 Q 68 57 63 82',sw=1.2,line=tint(color,.4))

    elif kind == 'kinase':
        # Abstract bilobed enzyme; no persistent ATP or structural model is
        # asserted. A continuous silhouette avoids the old bowl-like icon.
        path('M 13 36 C 7 15 37 5 54 17 C 68 7 90 19 88 36 C 86 48 72 49 66 47 L 58 52 C 78 48 95 64 86 80 C 76 99 40 94 24 80 C 10 70 8 53 18 44 Z',fill=light,sw=1.6)
        path('M 18 44 Q 36 55 58 52 Q 68 51 73 56',line=tint(color,.3),sw=1.2)

    elif kind == 'tf':
        # Dimeric transcription factor docking into DNA major grooves
        # Left subunit
        path('M 8 48 C 6 22 34 14 46 28 L 48 68 C 30 78 10 72 8 48 Z', fill=light, line=stroke, sw=1.4)
        path('M 16 42 C 14 26 32 20 40 30 L 42 58 C 30 64 16 60 16 42 Z', fill='#ffffff', line='none', sw=0)
        # Right subunit
        path('M 92 48 C 94 22 66 14 54 28 L 52 68 C 70 78 90 72 92 48 Z', fill=mid, line=stroke, sw=1.4)
        # Basic recognition helices inserting into DNA
        rect(32, 68, 7, 24, rx=3, fill=dark, line=stroke, sw=1.2)
        rect(61, 68, 7, 24, rx=3, fill=dark, line=stroke, sw=1.2)

    elif kind == 'dna':
        # High-fidelity 3D DNA double helix with 13 paired base rungs and helical ribbon grooves
        for i in range(13):
            x = 4 + i * 7.6
            y1 = 50 + 26 * math.sin(i * math.pi / 3)
            y2 = 50 - 26 * math.sin(i * math.pi / 3)
            # Base pair rungs: Adenine/Thymine or Guanine/Cytosine pairing
            ymid = (y1 + y2) / 2
            path(f'M {x:.2f} {y1:.2f} L {x:.2f} {ymid:.2f}', line='#3f789e', sw=1.6)
            path(f'M {x:.2f} {ymid:.2f} L {x:.2f} {y2:.2f}', line='#d9824c', sw=1.6)
            circle(x, ymid, 1.2, fill='#ffffff', line='none', sw=0)
        # Two intertwined sugar-phosphate strands
        path('M 4 50 C 20 0 32 0 49 50 S 78 100 96 50', line=stroke, sw=2.4)
        path('M 4 50 C 20 100 32 100 49 50 S 78 0 96 50', line=stroke, sw=2.4)

    elif kind == 'mrna':
        # Single-stranded transcript with 5-cap, codon ticks, and poly-A tail
        circle(6, 50, 4.5, fill='#d9824c', line='#944d20', sw=1.2)
        path('M 10 50 Q 20 16 30 50 T 50 50 T 70 50 T 84 50', line=stroke, sw=2.4)
        for x in range(14, 82, 6):
            path(f'M {x} 51 L {x+1.5} 64', line=tint(color, 0.3), sw=1.5)
        path('M 84 50 Q 88 42 92 50 T 98 50', line='#d9824c', sw=2.0)

    elif kind == 'lipid':
        # Phospholipid molecule with hydrophilic head, glycerol bridge, and dual fatty acid tails
        circle(50, 26, 17, fill=light, line=stroke, sw=1.4)
        circle(45, 21, 5, fill='#ffffff', line='none', sw=0)
        # Saturated and unsaturated (kinked) acyl tails
        path('M 43 43 Q 34 66 42 92', line=stroke, sw=2.2)
        path('M 57 43 Q 66 60 74 72 Q 78 82 72 92', line=stroke, sw=2.2)
        phosphate_sites = ((30, 15), (70, 15)) if state == 'bisphosphate' else ((30, 15), (50, 8), (70, 15)) if state == 'trisphosphate' else ()
        for x, y in phosphate_sites:
            circle(x, y, 6.5, fill='#f2af58', line='#ab7226', sw=1.2)

    elif kind in ('vesicle', 'mvb'):
        # Bilayer vesicle with surface tetraspanins or MVB packed with intraluminal vesicles (ILVs)
        circle(50, 50, 44, fill=light, line=stroke, sw=1.6)
        circle(50, 50, 37, fill='none', line=tint(color, 0.4), sw=1.0)
        circle(36, 32, 10, fill='#ffffff', line='none', sw=0)
        if kind == 'mvb':
            spots = [(32, 32), (64, 30), (28, 62), (62, 62), (48, 48), (44, 26), (50, 70)]
            for x, y in spots:
                circle(x, y, 7.5, fill=mid, line=stroke, sw=1.1)
                circle(x-1.5, y-1.5, 2, fill='#ffffff', line='none', sw=0)
        else:
            # Surface markers (tetraspanins CD63/CD81)
            for a in (0, 72, 144, 216, 288):
                rad = math.radians(a)
                x, y = 50 + 44 * math.cos(rad), 50 + 44 * math.sin(rad)
                circle(x, y, 3.5, fill='#d9824c', line='#944d20', sw=0.9)

    elif kind == 'vesicle_fusion':
        # Omega-shaped exocytic membrane fusion pore
        path('M 2 76 L 24 76 C 36 76 38 64 32 50 C 20 18 80 14 74 50 C 68 64 70 76 82 76 L 98 76', fill=light, line=stroke, sw=2.0)
        path('M 2 82 L 24 82 C 42 82 44 64 38 52 C 28 26 72 22 66 52 C 60 64 64 82 82 82 L 98 82', fill='none', line=tint(color, 0.4), sw=1.2)
        # Escaping intraluminal vesicles (exosomes) into extracellular space
        circle(50, 36, 7.5, fill=mid, line=stroke, sw=1.2)
        circle(38, 22, 6, fill=mid, line=stroke, sw=1.0)
        circle(62, 20, 5.5, fill=mid, line=stroke, sw=1.0)

    elif kind == 'nucleus':
        # Eukaryotic double-membrane nuclear envelope with nuclear pore complexes, nucleolus, and chromatin
        ellipse(50, 50, 47, 43, fill=light, line=stroke, sw=1.6)
        ellipse(50, 50, 42, 38, fill=tint(color, 0.94), line=tint(color, 0.45), sw=1.0)
        # Nuclear pore complex beads along envelope
        for a in range(0, 360, 40):
            rad = math.radians(a)
            x, y = 50 + 44.5 * math.cos(rad), 50 + 40.5 * math.sin(rad)
            ellipse(x, y, 2.8, 2.2, fill='#ffffff', line=stroke, sw=0.8)
        # Dense nucleolus
        ellipse(62, 42, 13, 11, fill=mid, line=stroke, sw=1.1)
        ellipse(60, 40, 5, 4, fill=tint(color, 0.3), line='none', sw=0)
        # Chromatin fibers
        path('M 18 52 Q 32 30 40 56 T 68 62 T 82 36', line=tint(color, 0.45), sw=1.4)

    elif kind == 'mitochondrion':
        # Double-membrane organelle with deeply folded transverse inner cristae and matrix
        path('M 10 36 C 28 6 82 12 92 40 C 102 74 58 94 24 84 C 2 76 0 54 10 36 Z', fill=light, line=stroke, sw=1.6)
        path('M 16 40 C 32 18 78 22 84 44 C 90 68 58 84 30 76 C 14 70 10 54 16 40 Z', fill='none', line=tint(color, 0.5), sw=1.0)
        # Deeply folded cristae
        path('M 22 34 Q 40 60 26 70 M 38 26 Q 58 56 42 78 M 56 26 Q 78 54 58 76 M 72 32 Q 88 56 74 68', line=stroke, sw=1.8)
        # Matrix granules (ATP synthase / mtDNA)
        circle(35, 46, 1.8, fill='#d9824c', line='none', sw=0)
        circle(52, 60, 1.8, fill='#d9824c', line='none', sw=0)
        circle(66, 42, 1.8, fill='#d9824c', line='none', sw=0)

    elif kind in ('golgi', 'er'):
        # Stacked crescent cisternae with dilated rims and budding transport vesicles
        for i in range(5):
            y = 14 + i * 14.5
            path(f'M {12+i*2.5} {y} Q 50 {y-11} {88-i*2.5} {y} L {85-i*2.5} {y+8} Q 50 {y-2} {15+i*2.5} {y+8} Z', fill=light, line=stroke, sw=1.3)
        if kind == 'er':
            # Ribosome studs along rough ER cisternae
            for y in (15, 29, 44, 59, 74):
                for x in (22, 36, 50, 64, 78):
                    circle(x, y, 1.4, fill=dark, line='none', sw=0)
        else:
            # Budding coated vesicles at lateral rims
            circle(10, 36, 4.5, fill=mid, line=stroke, sw=1.0)
            circle(90, 52, 4.5, fill=mid, line=stroke, sw=1.0)

    elif kind in ('cell', 'tumor_cell', 'immune_cell'):
        if kind == 'tumor_cell':
            # Pleomorphic malignant cell with irregular invadopodia and lobed nucleus
            path('M 14 18 Q 31 1 48 11 Q 73 -1 86 23 Q 104 37 90 56 Q 99 79 78 87 Q 59 105 43 90 Q 18 98 14 76 Q -1 57 11 43 Q 2 30 14 18 Z', fill=light, line=stroke, sw=1.6)
            # Enlarged irregular multi-lobed nucleus
            path('M 32 32 Q 52 18 68 32 Q 82 48 64 68 Q 38 84 28 62 Q 20 44 32 32 Z', fill=mid, line=stroke, sw=1.4)
            circle(48, 44, 4.5, fill=deep, line='none', sw=0)
        elif kind == 'immune_cell':
            # Amoeboid leukocyte with pseudopodia and indented nucleus
            path('M 18 24 Q 40 8 68 18 Q 94 28 88 56 Q 96 82 72 88 Q 42 98 24 82 Q 4 68 12 44 Q 6 30 18 24 Z', fill=light, line=stroke, sw=1.5)
            # Reniform (kidney-shaped) indented nucleus
            path('M 34 36 C 46 26 64 28 68 42 C 72 56 64 70 50 72 C 38 74 28 62 32 50 C 36 46 42 48 40 42 C 38 38 32 40 34 36 Z', fill=mid, line=stroke, sw=1.2)
            # Cytotoxic granules
            for gx, gy in ((22, 60), (30, 72), (64, 76), (78, 62), (76, 38)):
                circle(gx, gy, 2.2, fill='#d9824c', line='none', sw=0)
        else:
            st = str(state or '').lower().strip()
            from scientific_intent import labeled_cell_phase
            aliases={'apoptotic':'apoptotic','apoptosis':'apoptotic','apoptotic cell':'apoptotic','凋亡':'apoptotic','凋亡细胞':'apoptotic',
                     'g1':'interphase','s_phase':'interphase','g2':'interphase','quiescent':'interphase'}
            st=labeled_cell_phase(st,biological_context=True) or aliases.get(st,'')
            if any(k in st for k in ('cytokinesis', '胞质分裂', 'daughter', 'cleavage')):
                # Cytokinesis: deep equatorial furrow dividing cell into two daughter cells
                path('M 50 46 C 45 32 30 18 16 26 C 2 34 2 66 16 74 C 30 82 45 68 50 54 C 55 68 70 82 84 74 C 98 66 98 34 84 26 C 70 18 55 32 50 46 Z', fill=light, line=stroke, sw=1.6)
                circle(50, 50, 2.5, fill='#EA580C', line='#C2410C', sw=0.8)
                circle(25, 50, 12, fill=mid, line=stroke, sw=1.2)
                circle(22, 47, 2.5, fill=deep, line='none', sw=0)
                path('M 21 52 Q 25 55 29 51 M 23 46 Q 27 49 29 45', line=shade(color, 0.35), sw=0.7)
                circle(75, 50, 12, fill=mid, line=stroke, sw=1.2)
                circle(72, 47, 2.5, fill=deep, line='none', sw=0)
                path('M 71 52 Q 75 55 79 51 M 73 46 Q 77 49 79 45', line=shade(color, 0.35), sw=0.7)
            elif any(k in st for k in ('telophase', '末期')):
                # Telophase: elongated cell with emerging cleavage furrow and two reforming nuclei
                path('M 50 22 C 30 14 10 24 10 50 C 10 76 30 86 50 78 C 70 86 90 76 90 50 C 90 24 70 14 50 22 Z', fill=light, line=stroke, sw=1.6)
                path('M 50 18 L 50 24 M 50 76 L 50 82', line='#EA580C', sw=2.0)
                ellipse(28, 50, 15, 14, fill=tint(color, 0.65), line=stroke, sw=1.1, stroke_dasharray='4 2')
                ellipse(72, 50, 15, 14, fill=tint(color, 0.65), line=stroke, sw=1.1, stroke_dasharray='4 2')
                path('M 22 48 Q 28 42 34 50 M 24 54 Q 28 58 32 52', line='#BE185D', sw=1.5)
                path('M 66 48 Q 72 42 78 50 M 68 54 Q 72 58 76 52', line='#BE185D', sw=1.5)
                path('M 46 50 H 54', line='#10B981', sw=1.2)
            elif any(k in st for k in ('anaphase', '后期')):
                # Anaphase: elongated cell with sister chromatids separated into V-shapes pulled to poles
                ellipse(50, 50, 47, 39, fill=light, line=stroke, sw=1.6)
                circle(10, 50, 2.8, fill='#F59E0B', line='#D97706', sw=0.9)
                circle(90, 50, 2.8, fill='#F59E0B', line='#D97706', sw=0.9)
                path('M 12 50 L 30 35 M 12 50 L 32 45 M 12 50 L 32 55 M 12 50 L 30 65', line='#10B981', sw=1.1)
                path('M 88 50 L 70 35 M 88 50 L 68 45 M 88 50 L 68 55 M 88 50 L 70 65', line='#10B981', sw=1.1)
                path('M 36 47 H 64 M 36 53 H 64', line='#34D399', sw=0.9, stroke_dasharray='3 2')
                path('M 36 31 L 30 35 L 36 39', line='#BE185D', sw=2.6)
                path('M 38 41 L 32 45 L 38 49', line='#831843', sw=2.6)
                path('M 38 51 L 32 55 L 38 59', line='#BE185D', sw=2.6)
                path('M 36 61 L 30 65 L 36 69', line='#831843', sw=2.6)
                path('M 64 31 L 70 35 L 64 39', line='#BE185D', sw=2.6)
                path('M 62 41 L 68 45 L 62 49', line='#831843', sw=2.6)
                path('M 62 51 L 68 55 L 62 59', line='#BE185D', sw=2.6)
                path('M 64 61 L 70 65 L 64 69', line='#831843', sw=2.6)
            elif any(k in st for k in ('prometaphase', '前中期')):
                # Prometaphase: dissolving nuclear envelope, invading microtubules, congregating chromosomes
                ellipse(50, 50, 44, 43, fill=light, line=stroke, sw=1.6)
                path('M 32 30 Q 36 28 40 31 M 60 28 Q 64 30 68 28 M 30 66 Q 34 68 38 66 M 62 68 Q 66 66 70 69', line=stroke, sw=1.0, stroke_dasharray='2 2')
                circle(16, 50, 2.8, fill='#F59E0B', line='#D97706', sw=0.8)
                circle(84, 50, 2.8, fill='#F59E0B', line='#D97706', sw=0.8)
                path('M 18 50 Q 32 40 44 44 M 18 50 Q 34 48 48 48 M 18 50 Q 32 60 46 56 M 82 50 Q 68 40 56 44 M 82 50 Q 66 48 52 48 M 82 50 Q 68 60 54 56', line='#10B981', sw=1.0)
                path('M 44 42 L 50 48 M 50 42 L 44 48', line='#BE185D', sw=2.4)
                path('M 48 52 L 54 58 M 54 52 L 48 58', line='#831843', sw=2.4)
            elif any(k in st for k in ('metaphase', '中期')):
                # Metaphase: chromosomes aligned on central equatorial plate with bipolar spindle apparatus
                ellipse(50, 50, 45, 42, fill=light, line=stroke, sw=1.6)
                circle(14, 50, 3.0, fill='#F59E0B', line='#D97706', sw=0.9)
                circle(86, 50, 3.0, fill='#F59E0B', line='#D97706', sw=0.9)
                path('M 16 50 Q 32 30 46 32 M 16 50 Q 33 41 46 44 M 16 50 L 46 56 M 16 50 Q 32 70 46 68', line='#10B981', sw=1.1)
                path('M 84 50 Q 68 30 54 32 M 84 50 Q 67 41 54 44 M 84 50 L 54 56 M 84 50 Q 68 70 54 68', line='#10B981', sw=1.1)
                path('M 16 50 Q 50 20 84 50 M 16 50 Q 50 80 84 50', line='#34D399', sw=0.8, stroke_dasharray='4 2')
                path('M 47 28 L 53 36 M 53 28 L 47 36', line='#BE185D', sw=2.8)
                circle(50, 32, 1.2, fill='#F59E0B', line='none', sw=0)
                path('M 47 40 L 53 48 M 53 40 L 47 48', line='#831843', sw=2.8)
                circle(50, 44, 1.2, fill='#F59E0B', line='none', sw=0)
                path('M 47 52 L 53 60 M 53 52 L 47 60', line='#BE185D', sw=2.8)
                circle(50, 56, 1.2, fill='#F59E0B', line='none', sw=0)
                path('M 47 64 L 53 72 M 53 64 L 47 72', line='#831843', sw=2.8)
                circle(50, 68, 1.2, fill='#F59E0B', line='none', sw=0)
            elif any(k in st for k in ('prophase', '前期')):
                # Prophase: chromosome condensation within an intact envelope; breakdown is prometaphase.
                ellipse(50, 50, 44, 43, fill=light, line=stroke, sw=1.6)
                ellipse(50, 50, 24, 22, fill=tint(color, 0.7), line=stroke, sw=1.2)
                path('M 40 40 L 48 48 M 48 40 L 40 48', line='#BE185D', sw=2.4)
                path('M 52 42 L 60 50 M 60 42 L 52 50', line='#BE185D', sw=2.4)
                path('M 42 52 L 50 60 M 50 52 L 42 60', line='#831843', sw=2.4)
                path('M 54 54 L 62 62 M 62 54 L 54 62', line='#831843', sw=2.4)
                circle(22, 34, 2.6, fill='#F59E0B', line='#D97706', sw=0.8)
                path('M 17 34 L 13 34 M 22 29 L 20 25 M 26 31 L 30 27 M 25 37 L 29 41 M 18 38 L 14 42', line='#10B981', sw=0.8)
                circle(78, 34, 2.6, fill='#F59E0B', line='#D97706', sw=0.8)
                path('M 83 34 L 87 34 M 78 29 L 80 25 M 74 31 L 70 27 M 75 37 L 71 41 M 82 38 L 86 42', line='#10B981', sw=0.8)
            elif any(k in st for k in ('apoptotic', 'apoptosis', '凋亡')):
                # Apoptotic: membrane blebbing and pyknotic fragmented chromatin
                path('M 20 20 Q 28 8 40 18 Q 56 6 68 18 Q 84 10 88 28 Q 100 44 88 58 Q 98 76 80 84 Q 60 98 44 86 Q 26 96 16 80 Q 2 64 14 50 Q 6 32 20 20 Z', fill=tint('#EF4444', 0.85), line='#B91C1C', sw=1.5)
                circle(38, 42, 6, fill='#7F1D1D', line='#450A0A', sw=1.0)
                circle(58, 46, 5, fill='#7F1D1D', line='#450A0A', sw=1.0)
                circle(48, 62, 5.5, fill='#7F1D1D', line='#450A0A', sw=1.0)
                circle(30, 60, 3.5, fill='#7F1D1D', line='#450A0A', sw=0.8)
            elif any(k in st for k in ('interphase', '间期', 'g1', 's_phase', 'g2', 'quiescent')):
                # Interphase: prominent intact envelope, nucleolus, diffuse chromatin mesh, centrosome pair
                ellipse(50, 50, 44, 43, fill=light, line=stroke, sw=1.6)
                ellipse(50, 50, 22, 20, fill=mid, line=stroke, sw=1.3)
                circle(44, 46, 4.2, fill=deep, line='none', sw=0)
                path('M 35 48 Q 42 41 50 50 T 65 47 M 39 55 Q 49 61 58 53 M 41 43 Q 49 37 59 43', line=shade(color, 0.45), sw=0.9)
                circle(30, 28, 2.2, fill='#EA580C', line='#C2410C', sw=0.6)
                circle(34, 26, 2.2, fill='#EA580C', line='#C2410C', sw=0.6)
            else:
                # Default resting cell with distinct nucleus and nucleolus
                ellipse(50, 50, 44, 43, fill=light, line=stroke, sw=1.5)
                ellipse(50, 50, 22, 19, fill=mid, line=stroke, sw=1.2)
                circle(46, 47, 4.0, fill=deep, line='none', sw=0)
                path('M 38 52 Q 44 46 50 54 T 62 50', line=shade(color, 0.35), sw=0.8)

    elif kind == 'fibroblast':
        # Spindle-shaped cell with tapering bipolar cytoplasmic extensions
        path('M 2 54 L 28 36 Q 44 16 60 36 L 98 48 L 66 60 Q 52 86 36 66 Z', fill=light, line=stroke, sw=1.5)
        ellipse(49, 50, 14, 9, fill=mid, line=stroke, sw=1.2)

    elif kind == 'endothelial':
        # Squamous elongated cell forming vascular endothelium
        path('M 4 22 Q 48 32 96 20 L 96 72 Q 50 64 4 76 Z', fill=light, line=stroke, sw=1.4)
        for x in (24, 52, 80):
            ellipse(x, 48, 10, 16, fill=mid, line=stroke, sw=1.1)

    elif kind == 'pathogen':
        # Icosahedral viral capsid with glycoprotein spike trimers and RNA/DNA core
        for a in range(0, 360, 45):
            rad = math.radians(a)
            x1, y1 = 50 + 31 * math.cos(rad), 50 + 31 * math.sin(rad)
            x2, y2 = 50 + 44 * math.cos(rad), 50 + 44 * math.sin(rad)
            path(f'M {x1:.2f} {y1:.2f} L {x2:.2f} {y2:.2f}', sw=1.8)
            circle(x2, y2, 3.2, fill=mid, line=stroke, sw=0.9)
        circle(50, 50, 31, fill=light, line=stroke, sw=1.6)
        path('M 38 42 Q 50 30 62 42 T 50 64 T 38 42', line=tint(color, 0.25), sw=1.8)

    elif kind == 'antibody':
        # Y-shaped immunoglobulin with two Fab antigen-binding arms, hinge, and Fc stem
        path('M 50 50 L 50 92', line=light, sw=6)
        path('M 50 50 L 20 16', line=light, sw=6)
        path('M 50 50 L 80 16', line=light, sw=6)
        path('M 50 50 L 50 92 M 50 50 L 20 16 M 50 50 L 80 16', line=stroke, sw=1.6)
        # Variable antigen-binding Fab tips
        rect(14, 10, 12, 10, rx=2, fill='#d9824c', line='#944d20', sw=1.1)
        rect(74, 10, 12, 10, rx=2, fill='#d9824c', line='#944d20', sw=1.1)
        # Fc constant domain
        rect(44, 76, 12, 16, rx=2, fill=mid, line=stroke, sw=1.1)

    elif kind == 'tissue':
        rect(3, 22, 94, 70, rx=4, fill=tint(color, 0.93), line=tint(color, 0.4), sw=1.1)
        path('M 3 22 Q 26 14 50 22 T 97 22 L 97 38 Q 76 30 50 38 T 3 38 Z', fill=mid, line=stroke, sw=1.1)
        if state == 'hemostasis':
            path('M 32 22 L 42 66 L 59 66 L 69 22', fill='#d99c94', line='#b7716b', sw=1.2)
            for x, y in ((43, 36), (54, 42), (47, 54), (60, 30)):
                circle(x, y, 5, fill='#d19a8d', line='#aa7366', sw=0.9)
        elif state == 'inflammation':
            path('M 34 22 L 43 68 L 58 68 L 67 22', fill=tint(color, 0.85), line=stroke, sw=1.1)
            for x, y in ((28, 60), (68, 58), (44, 72), (76, 74)):
                circle(x, y, 7, fill=mid, line=stroke, sw=1.1)
        else:
            for y in range(46, 88, 9):
                path(f'M 12 {y} Q 34 {y-6} 50 {y} T 88 {y}', line='#b39b79', sw=1.5)

    elif kind == 'collagen':
        for i in range(5):
            x = 8 + i * 18
            path(f'M {x} 6 Q {x+22} 35 {x} 65 Q {x-10} 85 {x+10} 94', line=stroke, sw=2.2)
            path(f'M {x+4} 7 Q {x+26} 35 {x+4} 65 Q {x-6} 85 {x+14} 94', line=tint(color, 0.4), sw=1.2)

    elif kind == 'complex':
        circle(32, 34, 22, fill=light, line=stroke, sw=1.5)
        circle(68, 34, 22, fill=mid, line=stroke, sw=1.5)
        circle(50, 66, 24, fill=dark, line=stroke, sw=1.5)
        circle(50, 44, 9, fill='#ffffff', line=stroke, sw=1.0)

    elif kind == 'domain':
        rect(6, 16, 88, 68, rx=8, fill=light, line=stroke, sw=1.4)
        path('M 18 32 Q 36 20 46 42 T 74 60', line=tint(color, 0.25), sw=1.5)

    elif kind == 'process':
        rect(4, 12, 92, 76, rx=10, fill=light, line=stroke, sw=1.5)
        path('M 20 34 L 70 34 M 20 50 L 80 50 M 20 66 L 60 66', line=tint(color, 0.25), sw=1.5)

    elif kind == 'text':
        pass

    else:
        ellipse(50, 50, 42, 32, fill=light, line=stroke, sw=1.4)

    return ''.join(p)
