"""Original, data-only discipline libraries. No model calls or downloaded artwork."""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scene_document import empty_scene,normalize_scene,audit_scene
from resource_packs import safe_svg,reflow_pack_scene,SAFE_ATTRS

ROOT=Path(__file__).resolve().parents[1]
INK='#395B70';BLUE='#84B7C8';PALE='#DFEDF1';TEAL='#79A99A';GOLD='#D5AA6C';RED='#C67F76'
def tag(name,**attrs):return '<'+name+' '+ ' '.join(k.replace('_','-')+'="'+html.escape(str(v),quote=True)+'"' for k,v in attrs.items())+'/>'
def path(d,fill='none',stroke=INK,sw=2):return tag('path',d=d,fill=fill,stroke=stroke,stroke_width=sw,stroke_linecap='round',stroke_linejoin='round')
def rect(x,y,w,h,fill=PALE,rx=2):return tag('rect',x=x,y=y,width=w,height=h,fill=fill,rx=rx,stroke=INK,stroke_width=2)
def circle(x,y,r,fill=PALE):return tag('circle',cx=x,cy=y,r=r,fill=fill,stroke=INK,stroke_width=2)
def ellipse(x,y,rx,ry,fill=PALE):return tag('ellipse',cx=x,cy=y,rx=rx,ry=ry,fill=fill,stroke=INK,stroke_width=2)
def line(x,y,u,v,color=INK,sw=2):return tag('line',x1=x,y1=y,x2=u,y2=v,stroke=color,stroke_width=sw,stroke_linecap='round')
def group(s,transform):return '<g transform="'+transform+'">'+s+'</g>'
def label(s,x=50,y=50,size=12):return '<text x="'+str(x)+'" y="'+str(y)+'" fill="'+INK+'" font-family="Arial" font-size="'+str(size)+'" text-anchor="middle">'+html.escape(s)+'</text>'
def svg(body):return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'+body+'</svg>'
def wave(y=50,color=BLUE):return path('M 8 '+str(y)+' C 20 '+str(y-30)+' 30 '+str(y-30)+' 42 '+str(y)+' S 66 '+str(y+30)+' 78 '+str(y)+' S 90 '+str(y-30)+' 96 '+str(y),stroke=color,sw=3)
def dots(rows=4,cols=4,dx=18,dy=18,x=23,y=23):return ''.join(circle(x+c*dx,y+r*dy,4,BLUE) for r in range(rows) for c in range(cols))
def gear():
    p=[]
    for n in range(32):
        a=n*math.pi/16;r=34 if n%4 in (0,1) else 26;p.append((50+r*math.cos(a),50+r*math.sin(a)))
    return path('M '+' L '.join(f'{x:.2f} {y:.2f}' for x,y in p)+' Z',PALE)+circle(50,50,12,'#FFFFFF')
def atom():return circle(50,50,6,GOLD)+''.join(group(ellipse(50,50,36,12,'none'),f'rotate({a} 50 50)') for a in (0,60,120))+circle(84,50,4,RED)
def molecule():return line(27,60,51,32)+line(51,32,77,57)+line(27,60,53,78)+line(53,78,77,57)+circle(27,60,12,BLUE)+circle(51,32,10,RED)+circle(77,57,11,TEAL)+circle(53,78,8,GOLD)
def graph():
    pts=[(18,28),(50,16),(82,34),(26,76),(72,80),(50,50)]
    return ''.join(line(*pts[a],*pts[b],BLUE) for a,b in [(0,1),(1,2),(0,3),(3,4),(4,2),(0,5),(2,5),(3,5),(4,5)])+''.join(circle(x,y,7,TEAL if i%2 else PALE) for i,(x,y) in enumerate(pts))
def database():return rect(20,22,60,58)+ellipse(50,22,30,10,BLUE)+path('M20 45 C20 59 80 59 80 45 M20 65 C20 79 80 79 80 65')
def layers():return ''.join(path(f'M12 {y} L55 {y-13} L90 {y+3} L47 {y+18} Z',color) for y,color in [(62,BLUE),(45,PALE),(28,TEAL)])
def flask():return path('M38 12 L62 12 L62 18 L58 18 L58 43 L83 79 Q88 89 75 90 L25 90 Q12 89 17 79 L42 43 L42 18 L38 18 Z',PALE)+path('M27 67 L73 67 L82 81 Q84 85 75 85 L25 85 Q16 85 20 80 Z',BLUE)+line(39,29,61,29)
def beaker():return path('M20 15 L78 15 L73 25 L73 83 Q73 90 66 90 L29 90 Q22 90 22 83 L22 22 Z',PALE)+path('M26 52 Q48 45 69 52 L69 82 Q69 85 64 85 L31 85 Q26 85 26 82 Z',BLUE)+''.join(line(26,y,35,y) for y in (30,40,50,60,70))
def electrode():return rect(39,12,22,67,TEAL)+line(50,12,50,3)+line(28,86,73,86,BLUE,4)
def battery():return rect(12,24,76,52)+rect(88,39,7,22,GOLD)+line(24,50,40,50)+line(32,42,32,58)+line(62,50,78,50)+rect(47,29,3,42,TEAL)
def lens():return path('M50 10 Q20 50 50 90 Q80 50 50 10 Z',PALE)+line(6,30,41,39,RED)+line(59,39,94,50,RED)+line(6,70,41,61,RED)+line(59,61,94,50,RED)
def spring():return path('M50 8 L50 18 L35 24 L65 33 L35 42 L65 51 L35 60 L65 69 L50 77 L50 91')
def cloud():return path('M22 66 C4 63 7 38 26 38 C25 12 65 10 71 35 C96 30 102 66 80 67 Z',PALE)
def tree():return rect(44,52,12,38,GOLD)+circle(34,42,20,TEAL)+circle(62,42,23,TEAL)+circle(49,22,21,TEAL)+line(50,62,50,31)
def vessel():return path('M5 30 Q30 48 48 35 T95 30 L95 68 Q70 50 50 65 T5 68 Z',PALE)+''.join(ellipse(x,49,7,4,RED) for x in (18,43,69,88))
def heart():return path('M50 86 C43 80 11 62 14 38 C16 15 39 15 49 34 C59 6 88 15 88 40 C87 60 65 76 50 86 Z',RED)+path('M48 33 L42 60 L56 65 L55 80',stroke='#FFFFFF')+path('M54 29 L57 9 L71 10 L69 31',TEAL)
def lung():return path('M44 30 C34 12 25 17 18 33 L9 70 Q8 88 34 84 L43 74 Z',BLUE)+path('M56 30 C66 12 75 17 82 33 L91 70 Q92 88 66 84 L57 74 Z',BLUE)+path('M48 9 L48 42 L30 58 M52 9 L52 42 L71 58',stroke=INK,sw=4)+line(29,59,21,72)+line(71,59,80,72)
def neuron():return circle(50,50,17,BLUE)+''.join(line(50+17*math.cos(a),50+17*math.sin(a),50+39*math.cos(a),50+39*math.sin(a),INK,2) for a in [n*math.pi/4 for n in range(8)])+circle(50,50,5,TEAL)

# Each dictionary entry specifies geometry, not a renamed generic rectangle.
SYMBOLS={
'beam_splitter':rect(21,21,58,58)+line(21,79,79,21,INK,3)+line(3,50,50,50,RED,2)+line(50,50,97,50,RED,2)+line(50,50,50,3,RED,2),
'potentiostat':rect(9,14,82,69)+rect(20,24,43,25,BLUE)+circle(77,35,5,GOLD)+''.join(circle(x,66,4,c) for x,c in ((28,RED),(50,TEAL),(72,BLUE))),
'beaker':beaker(),'flask':flask(),'tube':path('M35 10 L65 10 L65 74 C65 96 35 96 35 74 Z',PALE)+path('M39 49 L61 49 L61 74 C61 89 39 89 39 74 Z',BLUE),
'burette':rect(44,8,12,65)+line(50,73,50,89)+line(37,70,64,70,RED,4)+''.join(line(45,y,50,y) for y in range(17,62,8)),
'condenser':group(rect(38,12,24,76)+line(50,4,50,96)+path('M42 18 L58 28 L42 38 L58 48 L42 58 L58 68 L42 78'), 'rotate(25 50 50)'),
'funnel':path('M10 15 L90 15 L58 51 L58 87 L43 94 L43 51 Z',PALE)+line(15,23,85,23,BLUE,3),
'round_flask':path('M42 6 L58 6 L58 31 A31 31 0 1 1 42 31 Z',PALE)+path('M22 57 Q50 48 78 57 A28 28 0 0 1 22 57',BLUE),
'molecule':molecule(),'benzene':path('M50 12 L83 31 L83 69 L50 88 L17 69 L17 31 Z')+circle(50,50,23,'none'),
'catalyst':circle(50,50,31,TEAL)+circle(37,39,7,GOLD)+circle(62,60,7,GOLD)+path('M17 23 L8 15 M83 23 L92 15 M15 77 L7 85 M85 77 L93 85',stroke=GOLD),
'electrode':electrode(),'battery':battery(),'chromatogram':line(10,86,92,86)+line(10,86,10,10)+path('M10 82 L22 82 Q28 80 30 41 Q32 10 35 81 L47 81 Q51 80 55 54 Q59 25 63 80 L72 81 Q76 80 81 69 L87 82',stroke=BLUE,sw=3),
'stirrer':rect(15,65,70,22)+ellipse(50,65,35,7)+circle(69,78,4,GOLD)+group(beaker(),'translate(16 -6) scale(.68)'),
'balance':rect(20,78,60,10)+line(50,78,50,17)+line(18,30,82,30)+path('M18 30 L8 57 L30 57 Z',PALE)+path('M82 30 L70 57 L92 57 Z',PALE),
'droplet':path('M50 6 C43 27 20 46 20 66 A30 29 0 0 0 80 66 C80 46 57 27 50 6 Z',BLUE)+path('M34 63 Q28 77 45 82',stroke='#FFFFFF',sw=3),
'crystal':path('M50 7 L79 25 L87 67 L50 94 L13 67 L21 25 Z',PALE)+path('M21 25 L50 38 L79 25 M50 38 L50 94 M13 67 L50 53 L87 67'),
'column':rect(37,8,26,76)+''.join(circle(x,y,2,GOLD if y<40 else BLUE) for y in range(20,76,8) for x in (44,55))+line(50,84,50,95),
'lens':lens(),'mirror':line(48,8,48,92,INK,4)+''.join(line(48,y,61,y-10) for y in range(20,91,12))+path('M8 25 L47 50 L8 75',stroke=RED),
'laser':rect(8,35,49,30)+circle(57,50,13,TEAL)+line(70,50,96,50,RED,3)+''.join(line(18,y,40,y) for y in (43,50,57)),
'prism':path('M50 12 L91 85 L9 85 Z',PALE)+line(3,49,32,49,RED)+''.join(line(69,49,97,43+n*8,c) for n,c in enumerate((RED,GOLD,TEAL,BLUE))),
'slit':rect(44,5,12,35)+rect(44,60,12,35)+line(4,50,44,50,RED)+path('M58 44 Q80 50 58 56 M70 30 Q100 50 70 70',stroke=BLUE),
'screen':rect(16,13,68,63)+line(50,76,50,91)+line(31,91,69,91)+''.join(line(x,25,x,65,BLUE,4) for x in (34,48,62)),
'atom':atom(),'wave':wave(),'magnet':path('M20 18 L36 18 L36 58 C36 78 64 78 64 58 L64 18 L80 18 L80 59 C80 99 20 99 20 59 Z',PALE)+rect(20,18,16,21,RED)+rect(64,18,16,21,BLUE),
'coil':path('M5 67 L20 67 C32 67 17 25 30 25 C44 25 30 67 43 67 C56 67 43 25 56 25 C69 25 56 67 69 67 C82 67 69 25 82 25 L92 25'),
'pendulum':line(15,10,85,10,INK,4)+line(50,10,77,75)+circle(77,75,13,BLUE)+path('M15 66 Q39 94 77 92',stroke=GOLD),
'spring':spring(),'mass':rect(21,28,58,47,BLUE)+path('M9 80 L91 80 M12 85 L88 85')+circle(50,50,4,GOLD),
'charge':circle(50,50,24,RED)+line(38,50,62,50)+line(50,38,50,62)+''.join(line(50+30*math.cos(a),50+30*math.sin(a),50+43*math.cos(a),50+43*math.sin(a),GOLD) for a in [i*math.pi/4 for i in range(8)]),
'capacitor':line(5,50,42,50)+line(42,17,42,83,INK,4)+line(58,17,58,83,INK,4)+line(58,50,95,50),
'resistor':path('M5 50 L20 50 L25 33 L35 67 L45 33 L55 67 L65 33 L75 67 L80 50 L95 50'),
'detector':rect(29,18,46,64)+circle(52,48,17,BLUE)+circle(52,48,8,GOLD)+line(75,50,94,50)+line(52,82,52,94),
'polarizer':ellipse(50,50,30,39)+''.join(line(x,24,x,76,BLUE) for x in (35,45,55,65))+line(3,50,19,50,RED)+line(81,50,97,50,RED),
'particle':circle(50,50,29,BLUE)+circle(40,39,5,PALE)+circle(61,49,5,PALE)+circle(45,65,5,PALE),
'lattice':dots()+''.join(line(23,y,77,y,BLUE,1) for y in (23,41,59,77))+''.join(line(x,23,x,77,BLUE,1) for x in (23,41,59,77)),
'vacancy':''.join(circle(23+c*18,23+r*18,5,BLUE) for r in range(4) for c in range(4) if (r,c)!=(1,2))+circle(59,41,8,'none'),
'dislocation':''.join(line(x,15,x,85,BLUE) for x in (16,33,67,84))+path('M50 15 L50 46 L67 54 M16 35 L84 35 M16 65 L84 65'),
'layers':layers(),'graphene':''.join(group(path('M50 18 L76 34 L76 65 L50 81 L24 65 L24 34 Z'),f'translate({dx} {dy}) scale(.48)') for dx,dy in ((4,3),(29,3),(53,3),(16,26),(41,26),(4,49),(29,49),(53,49))),
'nanotube':ellipse(50,15,24,9)+path('M26 15 L26 83 M74 15 L74 83')+ellipse(50,83,24,9)+''.join(path(f'M27 {y} L73 {y+12} M27 {y+12} L73 {y}',stroke=TEAL,sw=1) for y in (22,40,58)),
'polymer':''.join(line(10+i*13,50+(-1)**i*12,23+i*13,50-(-1)**i*12,TEAL,3)+circle(10+i*13,50+(-1)**i*12,6,PALE) for i in range(6)),
'composite':rect(12,15,76,70)+''.join(line(18,y,82,y,TEAL,3) for y in (28,43,58,73))+''.join(circle(x,y,4,GOLD) for x,y in ((27,35),(60,50),(40,66),(73,22))),
'pore':rect(10,12,80,76,TEAL)+''.join(ellipse(x,y,7,5,'#FFFFFF') for x,y in ((26,30),(58,23),(76,46),(42,52),(23,72),(65,73))),
'membrane':rect(37,8,26,84,PALE)+''.join(circle(50,y,6,'#FFFFFF') for y in (21,40,59,78))+''.join(line(8,y,33,y,BLUE) for y in (30,66))+''.join(line(67,y,91,y,TEAL) for y in (30,66)),
'grain':path('M10 10 L90 10 L90 90 L10 90 Z',PALE)+path('M10 32 L35 43 L55 10 M35 43 L28 90 M35 43 L69 58 L90 35 M69 58 L68 90'),
'fiber':''.join(path(f'M12 {y} Q50 {y-20} 88 {y}',stroke=c,sw=5) for y,c in ((31,BLUE),(49,TEAL),(67,GOLD),(82,BLUE))),
'film':path('M10 65 L63 43 L91 57 L37 81 Z',PALE)+path('M10 52 L63 30 L91 44 L37 68 Z',BLUE)+line(38,68,38,81),
'substrate':path('M10 52 L63 30 L91 44 L37 68 Z',PALE)+path('M10 52 L10 64 L37 81 L91 57 L91 44 M37 68 L37 81'),
'tensile':rect(10,25,25,50,PALE)+rect(65,25,25,50,PALE)+path('M35 37 L45 45 L55 45 L65 37 L65 63 L55 55 L45 55 L35 63 Z',BLUE)+line(3,50,22,50,RED)+line(78,50,97,50,RED),
'fracture':rect(12,14,76,72)+path('M52 14 L43 35 L59 44 L40 64 L52 86',stroke=RED,sw=3),
'powder':''.join(circle(x,y,r,c) for x,y,r,c in ((25,75,10,BLUE),(46,72,13,TEAL),(70,77,11,GOLD),(37,50,9,BLUE),(62,47,13,TEAL),(51,24,8,GOLD))),
'pump':circle(52,50,29,BLUE)+path('M40 32 L71 50 L40 68 Z',PALE)+line(1,50,23,50,INK,5)+line(81,50,98,50,INK,5),
'valve':path('M14 27 L50 50 L86 27 L86 73 L50 50 L14 73 Z',PALE)+line(50,50,50,14)+line(34,14,66,14),
'pipe':path('M12 22 L62 22 Q83 22 83 43 L83 88 L62 88 L62 46 Q62 43 58 43 L12 43 Z',PALE)+line(10,17,10,47,BLUE,4)+line(56,90,89,90,BLUE,4),
'tank':rect(16,20,68,65)+ellipse(50,20,34,10)+path('M20 58 Q49 49 80 58 L80 80 L20 80 Z',BLUE)+line(30,85,30,96)+line(70,85,70,96),
'turbine':circle(50,50,36,'none')+''.join(group(path('M50 50 Q72 6 88 34 L59 54 Z',TEAL),f'rotate({a} 50 50)') for a in (0,120,240))+circle(50,50,8,GOLD),
'gear':gear(),'motor':rect(21,24,58,49,BLUE)+ellipse(21,48,10,24)+line(79,48,98,48,INK,6)+rect(34,15,28,9)+line(27,79,77,79,INK,4),
'sensor':circle(50,58,18,BLUE)+line(50,76,50,94)+path('M19 41 Q50 7 81 41 M29 47 Q50 24 71 47',stroke=TEAL,sw=3),
'chip':rect(25,25,50,50,TEAL)+rect(35,35,30,30,PALE)+''.join(line(x,12,x,25)+line(x,75,x,88)+line(12,x,25,x)+line(75,x,88,x) for x in (34,50,66)),
'actuator':rect(12,30,61,40)+rect(24,38,12,24,BLUE)+line(36,50,94,50,INK,5)+line(94,31,94,69,INK,4),
'robot':rect(20,83,60,9)+line(50,83,50,63,INK,7)+line(50,63,27,39,BLUE,9)+line(27,39,65,19,BLUE,9)+line(65,19,81,39,INK,6)+circle(50,63,9,GOLD)+circle(27,39,8,GOLD)+circle(65,19,7,GOLD)+path('M75 39 L78 50 L88 47'),
'heat_exchanger':rect(18,18,64,64)+path('M4 32 L75 32 L75 48 L25 48 L25 64 L96 64',stroke=RED,sw=3)+path('M35 3 L35 93 M62 3 L62 93',stroke=BLUE,sw=3),
'filter':path('M15 18 L85 18 L64 62 L64 86 L36 86 L36 62 Z',PALE)+''.join(line(25,y,75,y,TEAL) for y in (30,39,48))+line(42,93,59,93,BLUE,3),
'compressor':path('M14 17 L86 35 L86 65 L14 83 Z',PALE)+line(2,50,14,50,INK,4)+line(86,50,98,50,INK,4)+path('M30 32 L30 68 M48 36 L48 64 M66 40 L66 60',stroke=BLUE),
'fan':circle(50,50,38,'none')+''.join(group(path('M50 50 Q28 15 52 12 Q78 11 66 37 Z',BLUE),f'rotate({a} 50 50)') for a in (0,120,240))+circle(50,50,8,GOLD),
'nozzle':path('M10 26 L48 41 L73 41 L73 59 L48 59 L10 74 Z',PALE)+''.join(line(76,y,98,50,BLUE) for y in (35,50,65)),
'piston':rect(18,18,64,64)+rect(23,40,54,16,BLUE)+line(50,56,50,97,INK,6)+line(28,8,28,18)+line(71,8,71,18),
'truss':path('M7 78 L50 18 L93 78 Z')+path('M7 78 L36 78 L50 18 L64 78 L93 78 M27 49 L73 49 M36 78 L73 49 M64 78 L27 49',stroke=BLUE),
'mountain':path('M4 85 L38 20 L57 48 L72 13 L98 85 Z',PALE)+path('M27 40 L38 20 L50 38 L40 34 Z',BLUE)+path('M63 34 L72 13 L82 37 L72 30 Z',BLUE),
'river':path('M37 4 C94 34 1 40 57 65 C83 80 43 90 51 98 L75 98 C66 86 100 79 77 64 C17 34 100 32 58 4 Z',BLUE),
'aquifer':rect(8,12,84,76)+path('M9 32 L91 32 M9 59 L91 59')+path('M10 64 Q30 53 50 64 T90 64 L90 86 L10 86 Z',BLUE)+line(30,8,30,74,INK,3),
'soil':rect(23,8,54,84,GOLD)+path('M24 29 L76 29 M24 53 L76 53 M24 75 L76 75')+''.join(circle(x,y,2,PALE) for x,y in ((33,18),(61,23),(46,44),(68,64),(35,84))),
'cloud':cloud(),'rain':cloud()+''.join(line(x,75,x-6,90,BLUE,3) for x in (25,46,67,87)),
'sun':circle(50,50,21,GOLD)+''.join(line(50+29*math.cos(a),50+29*math.sin(a),50+43*math.cos(a),50+43*math.sin(a),GOLD,3) for a in [i*math.pi/4 for i in range(8)]),
'volcano':path('M4 88 L36 33 L64 33 L97 88 Z',GOLD)+path('M36 33 L49 45 L64 33',RED)+path('M43 28 Q25 13 44 9 M55 28 Q75 11 60 5',stroke=RED,sw=3),
'tree':tree(),'leaf':path('M17 83 Q5 20 83 14 Q96 84 17 83 Z',TEAL)+line(17,83,72,26)+path('M38 62 L29 37 M50 49 L70 55'),
'wetland':path('M4 75 Q25 65 48 75 T96 75 L96 92 L4 92 Z',BLUE)+''.join(line(x,75,x,25)+ellipse(x-5,30,5,12,TEAL) for x in (20,43,66,84)),
'ocean':''.join(path(f'M5 {y} Q17 {y-12} 30 {y} T55 {y} T80 {y} L95 {y}',stroke=BLUE,sw=3) for y in (31,50,69,86)),
'sediment':rect(10,12,80,76)+''.join(path(f'M11 {y} L32 {y-5} L59 {y+4} L89 {y-2}',stroke=c,sw=3) for y,c in ((29,GOLD),(48,RED),(67,BLUE))),
'glacier':path('M8 76 L27 26 L48 17 L64 39 L82 28 L94 77 Z',PALE)+path('M27 26 L33 61 L48 17 L55 71 L64 39 L72 70 L82 28',stroke=BLUE)+line(4,87,96,87,BLUE,3),
'watershed':path('M8 23 L40 13 L88 25 L92 78 L52 91 L11 76 Z',PALE)+path('M27 24 L49 49 L76 32 M29 75 L49 49 L60 84',stroke=BLUE,sw=4),
'pollutant':''.join(circle(x,y,r,c) for x,y,r,c in ((24,29,8,RED),(61,19,10,GOLD),(79,49,8,RED),(50,50,12,RED),(24,71,11,GOLD),(65,78,9,RED))),
'station':line(50,87,50,19)+line(29,88,71,88)+path('M50 20 L77 16 L77 35 L50 39 Z',TEAL)+circle(50,57,10,PALE)+line(12,42,45,42)+line(20,30,20,53),
'satellite':rect(37,34,26,32,GOLD)+rect(4,25,28,50,BLUE)+rect(68,25,28,50,BLUE)+path('M38 28 Q50 6 64 28 Z',PALE)+line(50,9,50,2)+''.join(line(x,27,x,73) for x in (13,23,77,87)),
'database':database(),'server':''.join(rect(16,y,68,20)+circle(26,y+10,3,TEAL)+line(44,y+10,75,y+10) for y in (14,40,66)),
'neuron':neuron(),'network':graph(),'tree_graph':line(50,20,24,52)+line(50,20,76,52)+line(24,52,11,82)+line(24,52,39,82)+line(76,52,65,82)+line(76,52,90,82)+''.join(circle(x,y,7,BLUE) for x,y in ((50,20),(24,52),(76,52),(11,82),(39,82),(65,82),(90,82))),
'tensor':path('M22 24 L64 11 L87 31 L87 74 L45 89 L22 68 Z',PALE)+path('M22 24 L45 44 L87 31 M45 44 L45 89 M35 19 L58 40 L58 84 M50 14 L72 36 L72 79 M23 45 L45 63 L87 50',stroke=BLUE),
'matrix':path('M23 12 L12 12 L12 88 L23 88 M77 12 L88 12 L88 88 L77 88')+''.join(rect(x,y,9,9,c) for x,y,c in ((28,23,BLUE),(46,23,TEAL),(64,23,GOLD),(28,45,TEAL),(46,45,GOLD),(64,45,BLUE),(28,67,GOLD),(46,67,BLUE),(64,67,TEAL))),
'embedding':line(15,86,91,86)+line(15,86,15,11)+''.join(circle(x,y,4,c) for x,y,c in ((28,28,BLUE),(37,23,BLUE),(31,39,BLUE),(68,63,TEAL),(78,70,TEAL),(62,75,TEAL),(69,28,GOLD),(81,22,GOLD))),
'gpu':rect(8,25,84,52,TEAL)+circle(35,50,18,PALE)+circle(72,50,13,PALE)+rect(19,77,48,9,GOLD)+line(35,33,35,67)+line(18,50,52,50),
'dataset':''.join(path(f'M{x} {y} L{x+36} {y} L{x+48} {y+12} L{x+48} {y+60} L{x} {y+60} Z',c) for x,y,c in ((29,9,PALE),(19,19,PALE),(9,29,BLUE)))+''.join(line(18,y,48,y) for y in (48,60,72)),
'loss':line(12,84,92,84)+line(12,84,12,10)+path('M18 20 C27 67 34 75 48 77 S74 79 89 79',stroke=RED,sw=3)+circle(51,77,4,GOLD),
'optimizer':ellipse(50,50,38,29,'none')+ellipse(50,50,25,18,'none')+ellipse(50,50,11,7,'none')+path('M18 26 L37 33 L29 43 L45 45 L50 50',stroke=RED,sw=3),
'decision':path('M50 8 L91 50 L50 92 L9 50 Z',PALE)+path('M37 42 Q50 24 61 38 Q67 50 50 56 L50 63')+circle(50,75,2,INK),
'mesh':path('M12 83 L25 22 L63 11 L90 49 L72 88 Z',PALE)+path('M12 83 L49 55 L25 22 L63 11 L49 55 L90 49 L72 88 L49 55 M25 22 L90 49 M12 83 L90 49',stroke=BLUE),
'field':''.join(line(x,y,x+12,y-7,BLUE)+path(f'M{x+8} {y-8} L{x+12} {y-7} L{x+11} {y-3}',stroke=BLUE) for x in (14,37,60,80) for y in (25,47,69,88)),
'code':path('M34 24 L10 50 L34 76 M66 24 L90 50 L66 76 M58 13 L42 87',stroke=TEAL,sw=4),
'split':path('M9 50 L43 50 L68 22 L91 22 M43 50 L68 78 L91 78',stroke=BLUE,sw=4)+circle(43,50,7,GOLD),
'heart':heart(),'lung':lung(),'brain':path('M49 15 C28 4 14 25 20 36 C4 45 12 67 24 67 C20 87 40 93 49 80 C58 95 81 85 78 70 C99 60 88 39 81 37 C88 20 66 7 52 18 Z',PALE)+path('M50 18 L50 81 M25 30 Q50 35 33 49 Q18 57 36 69 M67 25 Q52 37 69 46 Q87 54 65 70',stroke=RED),
'kidney':path('M57 9 C16 7 5 75 35 89 C62 102 89 78 67 64 C49 56 44 47 67 35 C85 24 73 10 57 9 Z',RED)+path('M59 40 L82 49 L82 95',stroke=BLUE,sw=4),
'liver':path('M9 33 Q42 5 89 27 L95 53 Q65 54 48 80 Q17 91 9 65 Z',RED)+path('M48 24 L48 76 M48 55 L72 52'),
'vessel':vessel(),'capillary':path('M5 22 C45 22 22 79 95 79 M5 42 C35 42 32 59 95 59',stroke=RED,sw=5)+''.join(circle(x,y,4,RED) for x,y in ((18,33),(44,50),(74,69))),
'syringe':group(rect(34,22,30,48)+rect(37,10,24,12)+line(49,70,49,97)+line(26,22,72,22)+''.join(line(36,y,45,y) for y in (33,44,55)),'rotate(28 50 50)'),
'tablet':group(path('M32 15 A18 18 0 0 1 68 15 L68 85 A18 18 0 0 1 32 85 Z',PALE)+path('M32 50 L68 50 L68 80 A18 18 0 0 1 32 80 Z',BLUE),'translate(0 6) scale(1 .85)'),
'ultrasound':rect(12,10,76,56)+path('M29 52 Q50 17 71 52 Z',BLUE)+rect(28,77,43,12)+line(50,66,50,77)+path('M88 52 Q98 65 84 83 L78 74'),
'mri':rect(12,12,76,70,PALE,9)+circle(50,43,25,BLUE)+circle(50,43,16,'#FFFFFF')+path('M34 53 L66 53 L77 91 L25 91 Z',GOLD),
'ecg':rect(7,16,86,65)+path('M12 51 L26 51 L33 42 L39 67 L48 28 L57 56 L65 51 L88 51',stroke=RED,sw=3),
'patient':circle(50,23,13,PALE)+path('M22 89 L22 55 Q22 42 50 42 Q78 42 78 55 L78 89 Z',BLUE)+line(50,44,50,89)+line(34,59,34,84)+line(66,59,66,84),
'hospital':rect(17,18,66,73)+rect(39,65,23,26)+rect(34,28,32,9,RED)+rect(46,20,9,26,RED)+''.join(rect(x,50,9,9) for x in (26,46,66)),
'stethoscope':path('M24 8 L24 38 C24 68 67 68 67 38 L67 8 M45 62 L45 78 C45 99 84 95 84 74',stroke=INK,sw=4)+circle(84,65,12,BLUE)+circle(84,65,6,PALE)+line(24,8,29,8,BLUE,5)+line(62,8,67,8,BLUE,5),
'biomarker':molecule()+path('M12 14 L25 14 M18 8 L18 21',stroke=TEAL,sw=3),
'cohort':''.join(group(circle(50,22,14,PALE)+path('M22 88 L22 57 Q50 31 78 57 L78 88 Z',BLUE),f'translate({x} {y}) scale({s})') for x,y,s in ((2,35,.5),(45,35,.5),(23,0,.55))),
'iv':rect(32,14,38,53,PALE,7)+rect(38,32,26,25,BLUE)+line(50,3,50,14)+path('M50 67 L50 81 Q75 94 85 78',stroke=BLUE,sw=3),
}

PACKS={
'chemistry':('化学','实验器材、分子与反应', ['beaker:烧杯','flask:锥形瓶','tube:试管','burette:滴定管','condenser:冷凝管','funnel:漏斗','round_flask:圆底烧瓶','molecule:球棍分子','benzene:苯环','catalyst:催化位点','electrode:电极','battery:电化学电池','chromatogram:色谱峰','stirrer:磁力搅拌器','balance:天平','droplet:液滴','crystal:晶体','column:色谱柱']),
'physics':('物理学','光学、电磁与力学',['lens:透镜','mirror:反射镜','laser:激光器','prism:棱镜','slit:狭缝','screen:成像屏','atom:原子模型','wave:波动','magnet:磁铁','coil:线圈','pendulum:单摆','spring:弹簧','mass:质量块','charge:点电荷','capacitor:电容','resistor:电阻','detector:探测器','polarizer:偏振片']),
'materials':('材料科学','微结构、缺陷与制造',['particle:纳米颗粒','lattice:晶格','vacancy:空位缺陷','dislocation:位错','layers:层状材料','graphene:石墨烯晶格','nanotube:纳米管','polymer:聚合物链','composite:复合材料','pore:多孔材料','membrane:多孔膜','grain:多晶晶粒','fiber:纤维','film:薄膜','substrate:基底','tensile:拉伸试样','fracture:裂纹扩展','powder:粉末颗粒']),
'engineering':('工程技术','流体、机械与控制',['pump:泵','valve:阀门','pipe:弯管','tank:储罐','turbine:涡轮','gear:齿轮','motor:电动机','sensor:传感器','chip:控制芯片','actuator:执行器','robot:机械臂','heat_exchanger:换热器','filter:过滤器','compressor:压缩机','fan:风机','nozzle:喷嘴','piston:活塞','truss:桁架']),
'earth-environment':('地球与环境','地质、水循环与生态',['mountain:山地','river:河流','aquifer:含水层','soil:土壤剖面','cloud:云','rain:降水','sun:太阳','volcano:火山','tree:树木','leaf:叶片','wetland:人工湿地','ocean:海洋','sediment:沉积层','glacier:冰川','watershed:流域','pollutant:污染物','station:环境监测站','satellite:遥感卫星']),
'computing-math':('计算机与数学','数据、算法与数值计算',['database:数据库','server:服务器','neuron:神经元','network:图网络','tree_graph:树结构','tensor:张量','matrix:矩阵','embedding:特征嵌入','gpu:计算加速器','dataset:数据集','loss:损失函数','optimizer:优化器','decision:判定节点','mesh:计算网格','field:向量场','code:计算程序','split:数据划分','chip:处理芯片']),
'medicine':('医学','器官、诊疗与研究流程',['heart:心脏','lung:肺','brain:脑','kidney:肾脏','liver:肝脏','vessel:血管','capillary:毛细血管','syringe:注射器','tablet:药片','ultrasound:超声设备','mri:磁共振设备','ecg:心电图示意','patient:患者','hospital:医院','stethoscope:听诊器','biomarker:生物标志物','cohort:研究队列','iv:输液装置']),
}

# Objects: (asset, label, x, y); edges refer to object indices and state the mechanism.
TEMPLATES={
'chemistry':[
 ('titration','酸碱滴定装置',[('burette','Titrant',45,9),('flask','Analyte + indicator',45,64),('stirrer','Mixing',113,64),('droplet','Endpoint',113,9)],[(0,1,'Add dropwise'),(2,1,'Mix'),(1,3,'Detect endpoint')]),
 ('chromatography','色谱分离与检测',[('tube','Sample',13,18),('column','Stationary phase',66,18),('detector','Detector',122,18),('chromatogram','Separated peaks',122,75),('beaker','Mobile phase',66,75)],[(0,1,'Inject'),(4,1,'Elute'),(1,2,'Separate'),(2,3,'Record signal')]),
 ('electrochemistry','电化学三电极测量',[('electrode','Working electrode',15,65),('electrode','Counter electrode',75,65),('electrode','Reference electrode',135,65),('potentiostat','Potentiostat',75,8)],[(3,0,'Control potential'),(0,1,'Current path'),(2,3,'Sense potential')]),
 ('catalysis','催化反应与再生',[('molecule','Reactant',11,43),('catalyst','Catalytic site',63,43),('molecule','Product',125,43),('droplet','Co-reactant',63,8),('catalyst','Regenerated site',63,82)],[(0,1,'Adsorb'),(3,1,'React'),(1,2,'Desorb'),(1,4,'Regenerate'),(4,1,'Reuse')])],
'physics':[
 ('interference','分束与干涉测量',[('laser','Coherent source',9,43),('beam_splitter','Beam splitter',56,43),('mirror','Reference arm',103,9),('mirror','Measurement arm',103,79),('detector','Interference signal',149,43)],[(0,1,'Input'),(1,2,'Reference'),(1,3,'Probe'),(2,4,'Recombine'),(3,4,'Phase shift')]),
 ('polarization','偏振态分析',[('laser','Light source',10,43),('polarizer','Polarizer',54,43),('polarizer','Rotating analyser',101,43),('detector','Intensity',146,43),('wave','Incident field',54,8)],[(0,1,'Prepare'),(4,1,'Field direction'),(1,2,'Polarized light'),(2,3,'Measure')]),
 ('oscillation','受迫振动与位移测量',[('spring','Elastic element',21,13),('mass','Moving mass',21,69),('coil','Periodic drive',85,69),('sensor','Displacement sensor',137,69),('wave','Response',137,13)],[(0,1,'Restoring force'),(2,1,'Drive'),(1,3,'Displacement'),(3,4,'Readout')]),
 ('induction','电磁感应与负载',[('magnet','Moving magnet',15,38),('coil','Induction coil',70,38),('resistor','Electrical load',127,38),('detector','Current measurement',127,83),('wave','Changing flux',70,8)],[(0,1,'Magnetic flux'),(4,1,'Time variation'),(1,2,'Induced voltage'),(2,3,'Measure current')])],
'materials':[
 ('composite','复合材料制备与表征',[('powder','Filler',13,17),('polymer','Polymer matrix',13,74),('composite','Mix and cure',74,45),('tensile','Mechanical test',135,17),('fracture','Failure analysis',135,74)],[(0,2,'Disperse'),(1,2,'Crosslink'),(2,3,'Load'),(2,4,'Inspect')]),
 ('membrane','多孔膜选择性传输',[('particle','Feed particles',17,25),('membrane','Selective membrane',76,43),('particle','Retentate',17,83),('droplet','Permeate',138,43)],[(0,1,'Feed'),(1,2,'Retain'),(1,3,'Permeate')]),
 ('film','薄膜沉积与界面',[('powder','Precursor',15,15),('particle','Nucleation',76,15),('film','Film growth',136,15),('substrate','Substrate',76,78),('lattice','Microstructure',136,78)],[(0,1,'Deposit'),(3,1,'Surface sites'),(1,2,'Coalesce'),(2,4,'Characterize')]),
 ('defects','缺陷与材料失效',[('lattice','Initial lattice',14,41),('vacancy','Point defects',66,8),('dislocation','Dislocation motion',66,78),('fracture','Crack propagation',133,41),('tensile','Applied load',14,86)],[(0,1,'Defect formation'),(0,2,'Plastic deformation'),(4,2,'Stress'),(1,3,'Local concentration'),(2,3,'Damage accumulation')])],
'engineering':[
 ('fluid_loop','流体循环与监测',[('tank','Reservoir',15,18),('pump','Pump',74,18),('valve','Control valve',134,18),('filter','Filter',134,78),('sensor','Flow sensor',74,78)],[(0,1,'Supply'),(1,2,'Pressurize'),(2,3,'Regulate'),(3,4,'Monitor'),(4,0,'Return')]),
 ('control','闭环运动控制',[('chip','Controller',15,38),('actuator','Actuator',70,38),('robot','Plant',131,38),('sensor','Feedback sensor',72,85)],[(0,1,'Command'),(1,2,'Actuate'),(2,3,'Measure'),(3,0,'Feedback')]),
 ('heat_recovery','热回收与换热',[('tank','Hot reservoir',14,13),('heat_exchanger','Heat exchanger',74,42),('tank','Cooled outlet',135,13),('pump','Cold inlet',14,80),('tank','Heated outlet',135,80)],[(0,1,'Hot stream'),(3,1,'Cold stream'),(1,2,'Heat release'),(1,4,'Heat recovery')]),
 ('structure','结构加载与传感',[('actuator','Loading actuator',15,9),('truss','Test structure',75,42),('sensor','Strain sensors',135,9),('server','Acquisition',135,80),('chip','Load control',15,80)],[(0,1,'Apply load'),(1,2,'Measure strain'),(2,3,'Acquire'),(0,3,'Applied load'),(3,4,'Feedback'),(4,0,'Regulate')])],
'earth-environment':[
 ('water_cycle','流域水循环',[('cloud','Atmosphere',76,8),('mountain','Upland',15,43),('river','Surface runoff',76,48),('ocean','Receiving water',135,78),('aquifer','Groundwater',15,85)],[(0,1,'Precipitation'),(1,2,'Runoff'),(1,4,'Infiltration'),(4,2,'Baseflow'),(2,3,'Discharge'),(3,0,'Evaporation')]),
 ('carbon_cycle','陆地碳交换',[('cloud','Atmospheric carbon',76,8),('tree','Vegetation',15,43),('soil','Soil carbon',15,85),('river','River transport',76,84),('ocean','Aquatic carbon',135,43)],[(0,1,'Photosynthesis'),(1,0,'Respiration'),(1,2,'Litter input'),(2,0,'Decomposition'),(2,3,'Leaching'),(3,4,'Export')]),
 ('remediation','湿地污染物去除',[('pollutant','Contaminated inflow',13,43),('wetland','Treatment wetland',75,43),('river','Treated outflow',135,43),('soil','Sediment retention',75,86),('leaf','Plant uptake',75,8)],[(0,1,'Inflow'),(1,2,'Discharge'),(1,3,'Adsorption'),(1,4,'Uptake')]),
 ('earth_observation','多源环境观测',[('satellite','Remote sensing',14,10),('station','In situ station',14,77),('watershed','Study catchment',76,43),('database','Aligned observations',135,10),('mesh','Spatial model',135,77)],[(0,2,'Surface observation'),(1,2,'Ground observation'),(2,3,'Co-register'),(3,4,'Calibrate'),(1,4,'Validate')])],
'computing-math':[
 ('training','训练、验证与优化',[('dataset','Dataset',12,41),('split','Data split',57,41),('network','Training model',104,10),('loss','Validation loss',148,42),('optimizer','Parameter update',104,81)],[(0,1,'Partition'),(1,2,'Training set'),(1,3,'Held-out set'),(2,3,'Evaluate'),(3,4,'Optimize'),(4,2,'Update')]),
 ('message_passing','图网络消息传递',[('network','Input graph',13,43),('matrix','Node features',72,8),('neuron','Aggregation',72,78),('embedding','Graph embedding',135,43)],[(0,1,'Encode'),(0,2,'Neighbour messages'),(1,2,'Feature transform'),(2,3,'Readout')]),
 ('simulation','数值模拟与验证',[('mesh','Geometry and mesh',13,43),('code','Solver',74,43),('field','Computed field',135,43),('matrix','Boundary conditions',74,8),('loss','Convergence check',74,85)],[(0,1,'Discretize'),(3,1,'Constrain'),(1,2,'Solve'),(1,4,'Residual'),(4,1,'Refine')]),
 ('reproducibility','可复现计算流程',[('database','Versioned input',13,14),('code','Pinned program',13,78),('server','Execution environment',75,43),('dataset','Result artifacts',135,14),('tree_graph','Provenance',135,78)],[(0,2,'Read input'),(1,2,'Run'),(2,3,'Persist'),(2,4,'Record lineage'),(0,4,'Input version'),(1,4,'Code version')])],
'medicine':[
 ('trial','随机对照试验流程',[('cohort','Eligible cohort',11,43),('patient','Random allocation',58,43),('tablet','Intervention group',106,9),('patient','Control group',106,79),('biomarker','Prespecified endpoint',149,43)],[(0,1,'Enroll'),(1,2,'Randomize'),(1,3,'Randomize'),(2,4,'Follow up'),(3,4,'Follow up')]),
 ('distribution','药物分布与清除',[('syringe','Administration',13,44),('vessel','Circulation',72,44),('heart','Target tissue',135,9),('liver','Metabolism',135,45),('kidney','Excretion',135,82)],[(0,1,'Absorb'),(1,2,'Distribute'),(1,3,'Metabolize'),(1,4,'Clear')]),
 ('gas_exchange','肺部气体交换',[('lung','Alveolar compartment',25,23),('capillary','Pulmonary capillary',100,23),('heart','Systemic circulation',100,80),('vessel','Venous return',25,80)],[(0,1,'Oxygen diffusion'),(1,0,'Carbon dioxide diffusion'),(1,2,'Oxygenated blood'),(2,3,'Tissue exchange'),(3,1,'Return')]),
 ('imaging','影像采集与判读',[('patient','Participant',14,43),('mri','Imaging acquisition',69,43),('brain','Reconstructed image',128,10),('biomarker','Quantitative feature',128,80),('stethoscope','Clinical review',153,43)],[(0,1,'Acquire'),(1,2,'Reconstruct'),(2,3,'Segment and measure'),(2,4,'Interpret'),(3,4,'Support review')])],
}

def make_scene(pid,title,objects,edges,assets):
    scene=empty_scene(title,title);scene['layout']='network';scene['provenance']={'method':'original-discipline-template','example':pid}
    for i,(key,name,x,y) in enumerate(objects):
        aid=pid.replace('-','_')+'_'+key;meta=assets[aid]
        scene['objects'].append({'id':'o'+str(i),'type':'symbol','asset_id':aid,'asset_snapshot':{'svg':svg(SYMBOLS[key]),'meta':meta},'label':name,'x':x,'y':y,'w':19,'h':23,'font_size_pt':8})
    for i,(a,b,name) in enumerate(edges):
        edge={'id':'r'+str(i),'source':'o'+str(a),'target':'o'+str(b),'type':'sequence','label':name}
        if any(u==b and v==a for u,v,_ in edges):
            p,q=scene['objects'][a],scene['objects'][b];dx=q['x']-p['x'];dy=q['y']-p['y'];length=max(1,math.hypot(dx,dy))
            edge['control']={'x':(p['x']+q['x'])/2+9.5-20*dy/length,'y':(p['y']+q['y'])/2+11.5+20*dx/length}
        scene['relations'].append(edge)
    if title=='电化学三电极测量':
        scene['compartments']=[{'id':'electrolyte','kind':'compartment','label':'Shared electrolyte','x':8,'y':51,'w':164,'h':61}]
        for o in scene['objects'][:3]:o['compartment']='electrolyte'
    scene['style']['relation_labels']=True
    return normalize_scene(scene)

def preview(scene):
    import xml.etree.ElementTree as ET
    from scene_render import render_scene
    root=ET.fromstring(render_scene(scene))
    for child in list(root):
        if child.tag.split('}')[-1] in ('title','metadata'):root.remove(child)
    for node in root.iter():
        for attr in list(node.attrib):
            if attr not in SAFE_ATTRS:del node.attrib[attr]
    return safe_svg(ET.tostring(root,encoding='unicode'))

def build(output):
    output.mkdir(parents=True,exist_ok=True);catalog={'schema_version':1,'packs':[]}
    for pid,(title,description,definitions) in PACKS.items():
        folder=ROOT/'resource-packs'/pid;folder.mkdir(parents=True,exist_ok=True)
        for sub in ('assets','templates','previews'):(folder/sub).mkdir(exist_ok=True)
        assets={}
        for definition in definitions:
            key,name=definition.split(':');aid=pid.replace('-','_')+'_'+key
            item={'id':aid,'asset_id':aid,'label':name,'category':description,'type':'symbol','default_dim':[22,24],
                'file':'assets/'+key+'.svg','keywords':[key,name,title],'author':'Rylume contributors','license':'CC0 1.0',
                'license_url':'https://creativecommons.org/publicdomain/zero/1.0/','author_url':'https://github.com/zhao060206/Rylume',
                'source_url':'https://github.com/zhao060206/Rylume/tree/main/resource-packs/'+pid,'modifications':'Original vector artwork.'}
            assets[aid]=item;content=safe_svg(svg(SYMBOLS[key]));item['sha256']=hashlib.sha256(content.encode()).hexdigest();(folder/item['file']).write_text(content,encoding='utf8')
        templates=[]
        # Templates may use general-purpose symbols beyond the palette's starter 18.
        for tid,name,objects,edges in TEMPLATES[pid]:
            for key,_,_,_ in objects:
                aid=pid.replace('-','_')+'_'+key
                if aid not in assets:
                    item={'id':aid,'asset_id':aid,'label':{'potentiostat':'恒电位仪','beam_splitter':'分束器','detector':'检测器','database':'数据库','mesh':'计算网格','server':'数据采集器','droplet':'液滴'}.get(key,key.replace('_',' ')),'category':description,'type':'symbol','default_dim':[22,24],
                        'file':'assets/'+key+'.svg','keywords':[key,title],'author':'Rylume contributors','license':'CC0 1.0',
                        'license_url':'https://creativecommons.org/publicdomain/zero/1.0/','author_url':'https://github.com/zhao060206/Rylume',
                        'source_url':'https://github.com/zhao060206/Rylume/tree/main/resource-packs/'+pid,'modifications':'Original vector artwork.'}
                    assets[aid]=item;content=safe_svg(svg(SYMBOLS[key]));item['sha256']=hashlib.sha256(content.encode()).hexdigest();(folder/item['file']).write_text(content,encoding='utf8')
            scene=make_scene(pid,name,objects,edges,assets);scene['id']=pid.replace('-','_')+'_template_'+tid
            assert not audit_scene(scene)['errors']
            file='templates/'+tid+'.scene.json';thumb='previews/'+tid+'.svg'
            (folder/file).write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf8')
            (folder/thumb).write_text(safe_svg(preview(scene)),encoding='utf8')
            single='previews/'+tid+'-single.svg';(folder/single).write_text(preview(reflow_pack_scene(scene,90,150)),encoding='utf8')
            templates.append({'id':scene['id'],'title':name,'description':' · '.join(o[1] for o in objects),
                'file':file,'thumbnail':thumb,'thumbnail_single':single,'canvas_mm':[180,120],'family':'network','includes':[o[1] for o in objects],
                'keywords':[title,name],'object_count':len(objects),'relation_count':len(edges),'object_labels':[o[1] for o in objects]})
        manifest={'schema_version':1,'id':pid,'version':'1.0.0','title':title,'domain':pid,'min_app_version':'3.1.0',
            'license':'CC0-1.0','assets':list(assets.values()),'templates':templates}
        (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
        (folder/'LICENSE.txt').write_text('Original artwork and template geometry: CC0 1.0 Universal.\nRylume contributors. https://creativecommons.org/publicdomain/zero/1.0/legalcode\nScientific mechanisms are schematic and should be checked against the intended research context.\n',encoding='utf8')
        filename=f'rylume-pack-{pid}-1.0.0.zip';dest=output/filename
        with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for p in sorted(folder.rglob('*')):
                if p.is_file():
                    info=zipfile.ZipInfo(str(p.relative_to(folder)).replace('\\','/'),date_time=(2026,10,30,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
                    z.writestr(info,p.read_bytes())
        catalog['packs'].append({'id':pid,'version':'1.0.0','title':title,'domain':pid,'min_app_version':'3.1.0',
            'description':description,'asset_count':len(assets),'template_count':len(templates),'asset_name':filename,
            'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'size':dest.stat().st_size})
    (output/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf8')
    (ROOT/'assets/resource-catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'packs':len(catalog['packs']),'assets':sum(p['asset_count'] for p in catalog['packs']),'templates':sum(p['template_count'] for p in catalog['packs'])}))
    return catalog

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='out/resource-packs');args=parser.parse_args();build(Path(args.output).resolve())
