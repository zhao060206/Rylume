"""Original composition presets inspired by scientific figure reading patterns.

Presets move the same scene objects; they never add a biological relationship.
"""
from __future__ import annotations
import copy
import math
from scene_document import normalize_scene, SceneError

COLORWAYS = [
 {'id':'lagoon','title':'海盐蓝绿','palette':{'primary':'#2E6F83','secondary':'#669A83','accent':'#D99854'}},
 {'id':'ink','title':'墨蓝 · 珊瑚','palette':{'primary':'#35546F','secondary':'#8399AD','accent':'#C66A59'}},
 {'id':'sage','title':'鼠尾草 · 铜','palette':{'primary':'#416E60','secondary':'#94A990','accent':'#B97B49'}},
 {'id':'plum','title':'紫灰 · 金','palette':{'primary':'#685775','secondary':'#9295A9','accent':'#C39843'}},
 {'id':'accessible','title':'蓝橙 · 易区分','palette':{'primary':'#0072B2','secondary':'#009E73','accent':'#D55E00'}},
 {'id':'graphite','title':'石墨 · 单色','palette':{'primary':'#3B4652','secondary':'#697581','accent':'#9099A3'}},
 {'id':'nature','title':'深蓝 · 赤红','palette':{'primary':'#1F4E79','secondary':'#5D7A94','accent':'#C0392B'}},
 {'id':'cell','title':'靛青 · 暖橙','palette':{'primary':'#204060','secondary':'#4B7B9B','accent':'#E66A23'}},
 {'id':'rose','title':'玫瑰灰 · 蓝绿','palette':{'primary':'#9A6172','secondary':'#548A8F','accent':'#C39959'}},
 {'id':'forest','title':'森林绿 · 赤陶','palette':{'primary':'#376B59','secondary':'#8C9D78','accent':'#B7664C'}},
 {'id':'violet','title':'鸢尾紫 · 青绿','palette':{'primary':'#74629E','secondary':'#539995','accent':'#CE9654'}},
 {'id':'cobalt','title':'钴蓝 · 琥珀','palette':{'primary':'#3D6EAC','secondary':'#71999E','accent':'#C18A39'}},
 {'id':'earth','title':'赭石 · 橄榄','palette':{'primary':'#91684C','secondary':'#7A8D64','accent':'#AB6474'}},
 {'id':'slate','title':'青灰 · 梅红','palette':{'primary':'#4C7887','secondary':'#98A6A0','accent':'#B85B73'}},
 {'id':'marine','title':'海军蓝 · 松石','palette':{'primary':'#395A75','secondary':'#459B99','accent':'#DC8A5A'}},
 {'id':'berry','title':'浆果紫 · 沙金','palette':{'primary':'#8A557F','secondary':'#8B8EAC','accent':'#BE9D58'}},
]

TEMPLATES = [
 {'id':'signal_relay','title':'膜到细胞核 · 横向级联','family':'pathway','example':'jak_stat','description':'区室分明，受体与胞质级联顺序展开'},
 {'id':'signal_nucleus','title':'右侧细胞核 · 焦点构图','family':'pathway','example':'tgf_smad','description':'膜受体起点，右侧核内效应成为终点'},
 {'id':'signal_lipid','title':'膜脂转换 · 双层信号','family':'pathway','example':'egfr','description':'膜面反应与胞质信号分别成层'},
 {'id':'signal_vertical','title':'自上而下 · 纵向通路','family':'pathway','example':'jak_stat','description':'沿一条主轴阅读，适合单栏机制图'},
 {'id':'signal_compact','title':'紧凑通路 · 双行接力','family':'pathway','example':'tgf_smad','description':'胞质级联折返，减少长斜线'},
 {'id':'signal_horizontal','title':'宽幅通路 · 级联条带','family':'pathway','example':'egfr','description':'扩大膜下反应区域，突出分子关系'},
 {'id':'process_strip','title':'过程展开 · 横向阶段','family':'process','example':'exosome','description':'阶段沿时间方向展开，形态与状态可比较'},
 {'id':'process_steps','title':'过程展开 · 阶梯推进','family':'process','example':'exosome','description':'对角推进的连续过程，保留阶段顺序'},
 {'id':'process_vertical','title':'组织修复 · 纵向阶段','family':'process','example':'wound','description':'顺序由上到下，适合纵向图版'},
 {'id':'process_grid','title':'组织修复 · 四象限','family':'process','example':'wound','description':'按阅读顺序排列阶段，保持比较尺度'},
 {'id':'network_orbit','title':'细胞互作 · 中心辐射','family':'network','example':'tme','description':'中心细胞与周围微环境建立直接关系'},
 {'id':'network_columns','title':'细胞互作 · 双侧对话','family':'network','example':'tme','description':'左右展开促进与抑制，关系集中于中间'},
 {'id':'assembly_horizontal','title':'复合物组装 · 横向递进','family':'assembly','example':'nlrp3','description':'组分、聚合与效应按阅读顺序展开'},
 {'id':'assembly_tiers','title':'复合物组装 · 分层结构','family':'assembly','example':'nlrp3','description':'同组结构域共同排列，显示组成层次'},
 {'id':'workflow_strip','title':'实验路线 · 横向流程','family':'process','example':'workflow','description':'从样本到结果，器材与步骤一一对应'},
 {'id':'workflow_vertical','title':'实验路线 · 纵向流程','family':'process','example':'workflow','description':'纵向阅读，可扩展实验与分析步骤'},
 {'id':'signal_cell','title':'细胞剖面 · 核内焦点','family':'pathway','example':'jak_stat','description':'曲线核膜与顺序级联，突出入核后的功能'},
 {'id':'process_cell','title':'细胞全景 · 囊泡释放','family':'process','example':'exosome','description':'在细胞轮廓中展示运输与释放的空间位置'},
 {'id':'network_tissue','title':'组织情境 · 细胞互作','family':'network','example':'tme','description':'细胞沿组织环境分布，主要相互作用居中'},
 {'id':'signal_divergent','title':'通路分区 · 双排展开','family':'pathway','example':'egfr','description':'将现有分子按双排组织，保留原有科学关系'},
 {'id':'signal_convergent','title':'通路焦点 · 中央汇集','family':'pathway','example':'egfr','description':'将现有对象围绕中央区域布置，保留原有关系'},
 {'id':'signal_feedback','title':'弧线走廊 · 主线留白','family':'pathway','example':'jak_stat','description':'为现有连接保留弧线路径，不添加反馈机制'},
]

for _template in TEMPLATES:
    _template['canvas_mm'] = (
        [90,150] if _template['id'].endswith('vertical') else
        [180,70] if _template['id'] in ('process_strip','workflow_strip') else
        [180,85] if _template['id'] in ('signal_lipid','signal_horizontal','assembly_horizontal') else
        [180,120])

from scene_storyboards import storyboard_catalog
TEMPLATES += storyboard_catalog()
from scene_flows import flow_catalog, flow_layout_catalog
TEMPLATES += flow_catalog()
TEMPLATES += flow_layout_catalog()

from template_library import curate_catalog
curate_catalog(TEMPLATES)

def template_info(template_id):
    item=next((t for t in TEMPLATES if t['id']==template_id),None)
    if not item:raise SceneError('未知排版模板')
    return item

def apply_template(scene,template_id,colorway=None):
    item=template_info(template_id)
    scene=normalize_scene(copy.deepcopy(scene))
    family='pathway' if scene['compartments'] else scene['layout']
    if item.get('new_scene_only'):
        if scene.get('provenance',{}).get('example')!=item['example']:
            raise SceneError('此科学主题请在画廊新建，不能替换当前图的机制')
    elif family!=item['family']:
        raise SceneError('此模板适用于'+item['family']+'图；请在模板画廊创建对应样板')
    scene['style']['template']=template_id
    if colorway:
        color=next((x for x in COLORWAYS if x['id']==colorway),None)
        if not color:raise SceneError('未知配色')
        scene['style']['palette']=copy.deepcopy(color['palette']);scene['style']['colorway']=colorway
    if item.get('new_scene_only'):return normalize_scene(scene)
    for r in scene['relations']:r.pop('control',None)
    return place_template(scene)

def place_template(scene):
    from scene_render import DEFAULT_DIMS, layout_scene
    scene=copy.deepcopy(scene);tid=scene['style']['template'];item=template_info(tid)
    cw,ch=scene['canvas']['width_mm'],scene['canvas']['height_mm']
    if tid.startswith('layout_'):
        from scene_flows import place_flow_layout
        return place_flow_layout(scene)
    if item.get('new_scene_only'):
        # Scene coordinates are authored and subsequently user-editable.
        # Reapplying its style must never reconstruct an original over edits.
        return normalize_scene(scene)
    def put(o,cx,cy,w=None,h=None):
        dw,dh=DEFAULT_DIMS.get(o['type'], (18, 13));w=w or o.get('w',dw);h=h or o.get('h',dh)
        o.update(x=round(cx-w/2,4),y=round(cy-h/2,4),w=round(w,4),h=round(h,4),label_dx=0,label_dy=0)
    if item['family']=='pathway':
        scene['style']['template']=''
        scene=layout_scene(scene,force=True)
        scene['style']['template']=tid
        if cw<110:return normalize_scene(scene)
        comp={c['id']:c for c in scene['compartments']}
        nuclear=next((c for c in scene['compartments'] if c['kind']=='nucleus'),None)
        cytos=[o for o in scene['objects'] if comp.get(o.get('compartment'),{}).get('kind')=='cytoplasm']
        nucs=[o for o in scene['objects'] if comp.get(o.get('compartment'),{}).get('kind')=='nucleus']
        receptors=[o for o in scene['objects'] if o['type'] in ('receptor','receptor_dimer','gpcr')]
        
        top=57;bottom=(nuclear['y']-12 if nuclear else ch-17)
        if tid in ('signal_nucleus','signal_cell') and nuclear:
            nuclear.update(x=cw*.70,y=48,w=cw*.25,h=ch-58)
            for c in scene['compartments']:
                if c['kind']=='cytoplasm':c.update(x=8,y=39,w=cw*.64,h=ch-48)
            for i,o in enumerate(cytos):put(o,cw*(.15+.40*(i%2)),54+(ch-82)*(i//2)/max(1,math.ceil(len(cytos)/2)-1))
            for i,o in enumerate(nucs):put(o,cw*.825,62+(ch-86)*i/max(1,len(nucs)-1),min(o['w'],cw*.18),o['h'])
        elif tid=='signal_vertical':
            cols=2 if len(cytos)>2 else 1;rows=math.ceil(len(cytos)/cols)
            for i,o in enumerate(cytos):
                row,col=divmod(i,cols);put(o,cw*(.28+col*.43),top+(bottom-top)*row/max(1,rows-1))
        elif tid=='signal_divergent':
            for o in receptors:
                o['x']=cw*.15-o['w']/2
                for r in scene['relations']:
                    if r['target']==o['id']:
                        ligand=next((v for v in scene['objects'] if v['id']==r['source'] and v['type']=='ligand'),None)
                        if ligand:ligand['x']=cw*.15-ligand['w']/2
            half=math.ceil(len(cytos)/2)
            for i,o in enumerate(cytos):
                branch=0 if i<half else 1;idx=i if branch==0 else i-half
                span=max(1, (half-1) if branch==0 else (len(cytos)-half-1))
                x=cw*(.30+.40*(idx/max(1,span)))
                y=top+(bottom-top)*(.22 if branch==0 else .78)
                put(o,x,y)
            for i,o in enumerate(nucs):put(o,cw*(.45+.35*i/max(1,len(nucs)-1)),ch-16)
        elif tid=='signal_convergent':
            for idx,o in enumerate(receptors):
                rx=cw*(.20 if idx%2==0 else .60)
                o['x']=rx-o['w']/2
                for r in scene['relations']:
                    if r['target']==o['id']:
                        ligand=next((v for v in scene['objects'] if v['id']==r['source'] and v['type']=='ligand'),None)
                        if ligand:ligand['x']=rx-ligand['w']/2
            for i,o in enumerate(cytos):
                put(o,cw*(.25+.50*i/max(1,len(cytos)-1)),top+(bottom-top)*(.35 if i%2==0 else .65))
            for i,o in enumerate(nucs):put(o,cw*(.40+.30*i/max(1,len(nucs)-1)),ch-16)
        elif tid=='signal_feedback':
            for o in receptors:
                o['x']=cw*.18-o['w']/2
                for r in scene['relations']:
                    if r['target']==o['id']:
                        ligand=next((v for v in scene['objects'] if v['id']==r['source'] and v['type']=='ligand'),None)
                        if ligand:ligand['x']=cw*.18-ligand['w']/2
            cols=min(3,len(cytos));rows=math.ceil(len(cytos)/max(1,cols))
            for i,o in enumerate(cytos):
                row,col=divmod(i,max(1,cols));put(o,cw*(.22+.48*col/max(1,cols-1)),top+(bottom-top)*row/max(1,rows-1))
            for i,o in enumerate(nucs):put(o,cw*(.60+.25*i/max(1,len(nucs)-1)),ch-16)
        else:
            for o in receptors:
                o['x']=cw*.16-o['w']/2
                for r in scene['relations']:
                    if r['target']==o['id']:
                        ligand=next((v for v in scene['objects'] if v['id']==r['source'] and v['type']=='ligand'),None)
                        if ligand:ligand['x']=cw*.16-ligand['w']/2
            cols=min(4 if tid in ('signal_horizontal','signal_lipid') else 3,len(cytos));rows=math.ceil(len(cytos)/max(1,cols))
            for i,o in enumerate(cytos):
                row,col=divmod(i,max(1,cols))
                if row%2:col=cols-col-1
                put(o,22+(cw-47)*col/max(1,cols-1),top+(bottom-top)*row/max(1,rows-1))
        return normalize_scene(scene)
    objects=scene['objects'];n=len(objects)
    for c in scene['compartments']:c.update(x=7,y=7,w=cw-14,h=ch-14)
    if tid=='process_cell':
        for i,o in enumerate(objects):
            positions=[(32,51),(75,51),(118,75),(153,97)]
            x,y=positions[i%4];put(o,x*cw/180,y*ch/120,22 if i!=2 else 29,22 if i!=2 else 26)
    elif item['family']=='network':
        if not objects:return normalize_scene(scene)
        put(objects[0],cw*.50,ch*.48,28,25)
        others=objects[1:]
        for i,o in enumerate(others):
            if tid=='network_invasion':
                row=i%3;col=i//3;cols=max(1,math.ceil(len(others)/3))
                put(o,cw*(.18+.64*col/max(1,cols-1)),ch*(.25+.50*row/2))
            elif tid in ('network_columns','network_tissue') or cw<110:
                side=i%2;row=i//2;rows=math.ceil(len(others)/2)
                put(o,cw*(.17+.66*side),22+(ch-49)*row/max(1,rows-1))
            else:
                a=-math.pi/2+2*math.pi*i/max(1,len(others));put(o,cw/2+(cw/2-26)*math.cos(a),ch/2+(ch/2-24)*math.sin(a))
    elif tid=='assembly_tiers':
        groups={}
        for o in objects:groups.setdefault(o.get('group_id') or o['id'],[]).append(o)
        for row,items in enumerate(groups.values()):
            for i,o in enumerate(items):put(o,cw*(i+1)/(len(items)+1),18+(ch-42)*row/max(1,len(groups)-1))
    elif tid=='process_cycle':
        rx=(cw-36)/2;ry=(ch-36)/2
        for i,o in enumerate(objects):
            angle=-math.pi/2+2*math.pi*i/max(1,n)
            put(o,cw/2+rx*math.cos(angle),ch/2+ry*math.sin(angle))
    elif tid=='comparative_split':
        half=math.ceil(n/2)
        for i,o in enumerate(objects):
            side=0 if i<half else 1;idx=i if side==0 else i-half
            rows=half if side==0 else n-half
            put(o,cw*(.25 if side==0 else .75),18+(ch-36)*idx/max(1,rows-1))
    else:
        vertical=tid.endswith('vertical') or (cw<110 and n>3)
        cols=1 if vertical else 2 if tid=='process_grid' else min(n,6)
        rows=math.ceil(n/max(1,cols))
        for i,o in enumerate(objects):
            row,col=divmod(i,max(1,cols));w,h=DEFAULT_DIMS.get(o['type'], (18, 13))
            slot=(cw-16)/max(1,cols)
            scale=min(1,(slot-10)/w,((ch-20)/max(1,rows)-11)/h)
            w*=scale;h*=scale
            x=8+slot*(col+.5);y=16+(ch-37)*(row+.5)/max(1,rows)
            if tid=='process_steps':y=22+(ch-51)*i/max(1,n-1)
            put(o,x,y,w,h)
    return normalize_scene(scene)

def enrich_artwork(scene,example_id):
    """Exact fixture mappings; scientific identities and state-specific glyphs stay intact."""
    from scientific_library import library
    mapping={
        'tme':{'m2':'bio_macrophage','treg':'bio_t_lymphocyte','cd8':'bio_t_lymphocyte'},
        'workflow':{'sample':'bio_cell_complete','rna':'bio_rna'},
    }.get(example_id,{})
    for o in scene['objects']:
        aid=mapping.get(o['id'])
        if aid in library():o['asset_id']=aid
    return scene

def make_template(template_id,*,width_mm=None,height_mm=None,colorway=None):
    from scene_examples import make_example
    item=template_info(template_id)
    cw,ch=item['canvas_mm']
    scene = make_example(item['example'],width_mm=width_mm or cw,height_mm=height_mm or ch)
    enrich_artwork(scene, item['example'])
    return apply_template(scene,template_id,colorway)

def prepare_gallery():
    """Build static previews for the installed app; no model or network required."""
    from pathlib import Path
    import json
    from scene_render import render_scene
    from biology_glyphs import symbol
    from scene_assets import ASSET_CATEGORIES
    root=Path(__file__).resolve().parent/'ui/library';root.mkdir(exist_ok=True)
    manifest={}
    for t in TEMPLATES:
        scene=make_template(t['id'])
        (root/(t['id']+'.svg')).write_text(render_scene(scene),encoding='utf8')
        (root/(t['id']+'-single.svg')).write_text(
            render_scene(make_template(t['id'],width_mm=90,height_mm=150)),encoding='utf8')
        manifest[t['id']]={'object_labels':[o['label'] for o in scene['objects'] if o['role']=='entity'],
            'object_count':sum(o['role']=='entity' for o in scene['objects']),
            'relation_count':len(scene['relations']),
            'relation_types':sorted({r['type'] for r in scene['relations']})}
    (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    for c in ASSET_CATEGORIES:
        for a in c['items']:
            (root/('native_'+a['type']+'.svg')).write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -4 108 108">'+symbol(a['type'],'#3D8297','','#3D8297',1)+'</svg>',
                encoding='utf8')
    print(f'Gallery prepared: {len(TEMPLATES)} templates rendered to {root}')

if __name__=='__main__':prepare_gallery()
