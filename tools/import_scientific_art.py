"""Import pinned, attributed Bioicons SVGs after flat-vector and visual checks.

Usage: python tools/import_scientific_art.py --archive bioicons.tar.gz
       --commit FULL_SHA --report report.json
The archive is read in memory, never extracted or executed. No model or network.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
import tarfile
import xml.etree.ElementTree as ET
from urllib.parse import quote,unquote
from functools import lru_cache

from defusedxml.ElementTree import fromstring
from svgelements import SVG, Path as VectorPath, Shape
from PIL import Image, ImageChops, ImageFilter
import cairosvg

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from resource_packs import safe_svg
LICENSES={'cc-0':('CC0 1.0','https://creativecommons.org/publicdomain/zero/1.0/'),
          'cc-by-3.0':('CC BY 3.0','https://creativecommons.org/licenses/by/3.0/'),
          'cc-by-4.0':('CC BY 4.0','https://creativecommons.org/licenses/by/4.0/')}
CATEGORIES={
 'Human_physiology':('biology','器官与人体系统','organelle'),
 'Animals':('biology','模式生物','cell'), 'Blood_Immunology':('biology','免疫与血液','immune_cell'),
 'General_items':('biology','实验器材与流程','process'), 'Lab_apparatus':('biology','实验器材与流程','process'),
 'Microbiology':('biology','微生物','pathogen'), 'Intracellular_components':('biology','细胞器与囊泡','organelle'),
 'Nucleic_acids':('biology','核酸与转录调控','dna'), 'Plants_Algae':('biology','植物与藻类','cell'),
 'Chemistry':('chemistry','化学结构与实验','process'), 'Amino-Acids':('chemistry','氨基酸结构','process'),
 'Cell_membrane':('biology','膜结构与受体','membrane'), 'Genetics':('biology','核酸与转录调控','dna'),
 'Parasites':('biology','寄生虫','pathogen'), 'Receptors_channels':('biology','膜结构与受体','receptor'),
 'Scientific_graphs':('computing-math','数据与分析示意','process'), 'Tissues':('biology','组织与细胞外基质','tissue'),
 'Cell_culture':('biology','细胞培养','process'), 'Safety_symbols':('engineering','实验安全标识','process'),
 'Oncology':('biology','肿瘤与病理','tumor_cell'), 'Machine_Learning':('computing-math','机器学习与计算流程','process'),
 'Procedures':('medicine','医学操作','process'), 'People-Other':('medicine','人物与活动','process'),
 'Cell_types':('biology','细胞与微环境','cell'), 'Cell_lines':('biology','细胞系','cell'),
 'Chemo-_and_Bioinformatics':('computing-math','生物信息与计算','process'), 'Viruses':('biology','病原体与病毒','pathogen'),
 'Imaging':('biology','显微与成像','process'), 'Molecular_modelling':('chemistry','分子模拟','process'),
 'Computer_hardware':('computing-math','计算设备','process'), 'Genomics':('biology','基因组与测序','dna'),
 'Nanotechnology':('materials','纳米材料','process'), 'Peptides':('biology','多肽与蛋白','protein'),
 'Epigenetics':('biology','表观遗传','dna'), 'Extracellular_matrix':('biology','细胞外基质','collagen'),
 'Neuroscience':('biology','神经科学','cell'), 'Molecular_Biology':('biology','分子生物学','protein')}


def classify(category,name):
    domain,group,kind=CATEGORIES[category]
    lower=name.lower()
    if any(s in lower for s in ('cytoflex','flow_cytometer','flow-cytometer')):
        return 'biology','实验器材与流程','process'
    if category in ('Microbiology','General_items','Cell_culture','Imaging') and any(s in lower for s in
            ('microtube','eppendorf','micropipette','microplate','cryotube','cuvette','test-tube','test_tube','erlenmeyer','microscope')):
        return 'biology','实验器材与流程','process'
    if category=='Cell_culture' and 'embryo' in lower:return 'biology','发育与胚胎','cell'
    if category=='Molecular_modelling' and lower in ('gromacs','openmm','pymol','vmd','avogadro'):
        return 'computing-math','计算软件标识','symbol'
    return domain,group,kind


def flat_vector(source):
    root=fromstring(source)
    forbidden={'image','script','foreignObject','text','filter','mask','linearGradient','radialGradient'}
    nodes=list(root.iter())
    if len(nodes)>20000 or any(n.tag.split('}')[-1] in forbidden for n in nodes):
        raise ValueError('embedded, active, text or unsupported effects')
    if re.search(rb'@import|<!DOCTYPE|<!ENTITY',source,re.I):raise ValueError('external declarations')
    if any(not ref.strip(' \t\r\n\"\'').startswith('#') for ref in re.findall(r'url\(([^)]+)\)',source.decode('utf-8-sig'),re.I)):
        raise ValueError('external stylesheet reference')
    for node in nodes:
        for key,value in node.attrib.items():
            if key.split('}')[-1].lower().startswith('on'):raise ValueError('event attribute')
            if key.split('}')[-1] in ('href','src') and not value.startswith('#'):raise ValueError('external reference')
            if any(not ref.strip(' \t\r\n\"\'').startswith('#') for ref in re.findall(r'url\(([^)]+)\)',value,re.I)):
                raise ValueError('external style reference')
    document=SVG.parse(io.BytesIO(source),reify=True)
    bounds=document.bbox(with_stroke=True)
    if not bounds:raise ValueError('empty geometry')
    x,y,x2,y2=bounds;w,h=x2-x,y2-y
    if not all(math.isfinite(v) for v in (x,y,w,h)) or min(w,h)<=0 or not .08<w/h<12:
        raise ValueError('invalid or extreme bounds')
    out=ET.Element('svg',{'xmlns':'http://www.w3.org/2000/svg','viewBox':f'{x} {y} {w} {h}'})
    color=lambda c:'none' if c is None or c.value is None else '#%02x%02x%02x'%(c.red,c.green,c.blue)
    for shape in document.elements():
        if not isinstance(shape,Shape):continue
        path=VectorPath(shape);path.reify()
        if not path:continue
        attrs={'d':path.d(),'fill':color(shape.fill),'stroke':color(shape.stroke),'stroke-width':str(shape.implicit_stroke_width or 0)}
        for key in ('fill-rule','fill-opacity','stroke-opacity','opacity','stroke-linecap','stroke-linejoin'):
            if key in shape.values:attrs[key]=str(shape.values[key])
        ET.SubElement(out,'path',attrs)
    if not 0<len(out)<=2400:raise ValueError('empty or excessive path count')
    value=ET.tostring(out,encoding='unicode')
    if len(value.encode())>650000:raise ValueError('excessive vector complexity')
    return value,[x,y,w,h]


@lru_cache(maxsize=4)
def thumbnail(svg,size=160):
    # CairoSVG applies clipping; renderers that ignore it cannot validate flattening.
    png=cairosvg.svg2png(bytestring=svg,output_width=560,output_height=560)
    rgba=Image.open(io.BytesIO(png)).convert('RGBA')
    im=Image.new('RGB',rgba.size,'white');im.paste(rgba,mask=rgba.getchannel('A'))
    mask=ImageChops.difference(im,Image.new('RGB',im.size,'white')).convert('L').point(lambda v:255 if v>18 else 0)
    box=mask.getbbox()
    if not box:raise ValueError('blank rendering')
    im=im.crop(box);im.thumbnail((size-8,size-8),Image.Resampling.LANCZOS)
    output=Image.new('RGB',(size,size),'white');output.paste(im,((size-im.width)//2,(size-im.height)//2))
    return output


def visual_error(original,converted):
    a,b=thumbnail(original),thumbnail(converted.encode())
    delta=ImageChops.difference(a,b)
    # Average absolute channel difference after trimming viewport whitespace.
    return sum(i*n for i,n in enumerate(delta.convert('L').histogram()))/(255*a.width*a.height)


def dark_ink_recall(original,converted):
    """Small dark outlines must not disappear behind a good average pixel score."""
    a,b=thumbnail(original),thumbnail(converted.encode())
    source=a.convert('L').point(lambda p:255 if p<65 else 0)
    target=b.convert('L').filter(ImageFilter.MinFilter(3)).point(lambda p:255 if p<85 else 0)
    count=source.histogram()[255]
    if count<20:return 1.0
    overlap=ImageChops.multiply(source,target).histogram()[255]
    return overlap/count


def silhouette_recall(original,converted):
    """Catch lost clipping/shape boundaries, allowing one antialiasing pixel."""
    a,b=thumbnail(original).convert('L'),thumbnail(converted.encode()).convert('L')
    values=[]
    for threshold in (220,235,245):
        source=a.point(lambda p:255 if p<threshold else 0);target=b.point(lambda p:255 if p<threshold else 0)
        expanded_source=source.filter(ImageFilter.MaxFilter(3));expanded_target=target.filter(ImageFilter.MaxFilter(3))
        values.append(min(ImageChops.multiply(source,expanded_target).histogram()[255]/max(1,source.histogram()[255]),
                          ImageChops.multiply(target,expanded_source).histogram()[255]/max(1,target.histogram()[255])))
    return min(values)


def geometry(svg):
    root=ET.fromstring(svg)
    paths=[n.get('d','') for n in root.iter() if n.tag.split('}')[-1]=='path']
    return hashlib.sha256(''.join(paths).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--commit',required=True);parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--refresh-expansion',action='store_true',help='Reconvert this importer\'s expansion while retaining existing stable IDs')
    args=parser.parse_args()
    if not re.fullmatch('[a-f0-9]{40}',args.commit):raise ValueError('Full pinned commit required')
    dest=ROOT/'assets/bioicons';web=ROOT/'ui/library';manifest=dest/'manifest.json'
    entries=json.loads(manifest.read_text(encoding='utf8'))
    previous_expansion={e['asset_id'] for e in entries if e['asset_id'].startswith('biox_')}
    if args.refresh_expansion:entries=[e for e in entries if not e['asset_id'].startswith('biox_')]
    before=len(entries)
    known_paths={unquote(e['source_url'].split('/static/icons/')[-1]) for e in entries}
    hashes={geometry((web/(e['asset_id']+'.svg')).read_text(encoding='utf8')) for e in entries}
    known_ids={e['asset_id'] for e in entries}
    words=json.loads(Path(__file__).with_name('scientific_asset_terms.json').read_text(encoding='utf8'))
    rejected=[];added=[];duplicates=0
    with tarfile.open(args.archive) as archive:
        members=archive.getmembers();prefix=members[0].name.split('/')[0]
        if not prefix.endswith(args.commit):raise ValueError('Archive root does not match pinned commit')
        authors=json.loads(archive.extractfile(prefix+'/static/icons/authors.json').read())
        author_urls={re.sub(r'[-_ ]+',' ',k).lower():v for k,v in authors.items()}
        for member in sorted(members,key=lambda m:m.name):
            parts=member.name.split('/')
            if len(parts)!=7 or parts[1:3]!=['static','icons'] or not member.isfile() or not member.name.endswith('.svg'):continue
            _,_,_,lic,category,author,filename=parts
            if lic not in LICENSES or category not in CATEGORIES:continue
            source_path='/'.join(parts[3:])
            if source_path in known_paths:continue
            if member.size>1000000:rejected.append([source_path,'source above 1 MB']);continue
            try:
                source=archive.extractfile(member).read()
                converted,box=flat_vector(source)
                safe_svg(converted)
                digest=geometry(converted)
                if digest in hashes:duplicates+=1;continue
                error=visual_error(source,converted)
                if error>.035:raise ValueError('visual difference above 3.5%')
                ink=dark_ink_recall(source,converted)
                if ink<.94:raise ValueError('dark outline recall below 94%')
                silhouette=silhouette_recall(source,converted)
                if silhouette<.94:raise ValueError('silhouette recall below 94%')
                name=filename[:-4];tokens=re.sub(r'([a-z])([A-Z])',r'\1 \2',name).lower()
                tokens=re.split(r'[-_ ]+',tokens)
                cn=' '.join(dict.fromkeys(words[w] for w in tokens if w in words))
                label=(cn+' · ' if cn else '')+name.replace('_',' ').replace('-',' ')
                aid='biox_'+re.sub('[^a-z0-9_]','_',author.lower()+'_'+name.lower())[:55]+'_'+hashlib.sha256(source_path.encode()).hexdigest()[:8]
                if aid in known_ids:continue
                domain,group,kind=classify(category,name)
                for token,typ in [('mitochond','mitochondrion'),('nucleus','nucleus'),('golgi','golgi'),('endoplasm','er'),('receptor','receptor'),('antibod','antibody'),('ribosome','complex'),('vesicle','vesicle')]:
                    if domain=='biology' and token in name.lower():kind=typ;break
                width,height=(26,26*box[3]/box[2]) if box[2]>=box[3] else (26*box[2]/box[3],26)
                licence,url=LICENSES[lic];display_author='Servier Medical Art' if author=='Servier' else author.replace('_',' ').replace('-',' ')
                entry={'asset_id':aid,'type':kind,'label':label,'domain':domain,'category':group,
                       'default_dim':[round(width,2),round(height,2)],'thumbnail':'/ui/library/'+aid+'.svg',
                       'author':display_author,'author_url':author_urls.get(re.sub(r'[-_ ]+',' ',author).lower()) or 'https://bioicons.com/',
                       'license':licence,'license_url':url,'source_url':'https://github.com/duerrsimon/bioicons/blob/'+args.commit+'/static/icons/'+quote(source_path),
                       'sha256':hashlib.sha256(source).hexdigest(),'viewbox':box,'keywords':name+' '+category+' '+cn,
                       'modifications':'Styles and transforms flattened into editable paths with transformed stroke widths. Visual comparison passed; mean luminance difference '+str(round(error*100,2))+'%, dark-outline recall '+str(round(ink*100,2))+'%, silhouette recall '+str(round(silhouette*100,2))+'% after whitespace normalization.'}
                (dest/(aid+'.original.svg')).write_bytes(source);(web/(aid+'.svg')).write_text(converted,encoding='utf8')
                entries.append(entry);added.append(entry);hashes.add(digest);known_ids.add(aid)
                if len(added)%50==0:print('Imported',len(added),'new vector assets',flush=True)
            except Exception as exc:rejected.append([source_path,str(exc)[:180]])
        for lic in LICENSES:
            member=next((m for m in members if m.name.endswith('/static/icons/'+lic+'/LICENSE')),None)
            if member:(dest/('LICENSE-'+lic+'.txt')).write_bytes(archive.extractfile(member).read())
    manifest.write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf8')
    if args.refresh_expansion:
        for aid in previous_expansion-known_ids:
            for folder,suffix in ((dest,'.original.svg'),(web,'.svg')):
                file=(folder/(aid+suffix)).resolve()
                if file.parent!=folder.resolve() or not aid.startswith('biox_'):raise ValueError('Unsafe stale-asset cleanup')
                file.unlink(missing_ok=True)
    (dest/'ATTRIBUTION.md').write_text('# Scientific artwork credits\n\nCurated from [Bioicons](https://bioicons.com/). Each entry retains its own author, license, pinned source URL and original digest. Editable conversions and original files are retained separately; licenses do not apply to the whole software. New conversions pass a local rendered comparison; that check does not verify scientific meaning.\n\n'+'\n'.join('- '+e['label']+' — '+e['author']+', ['+e['license']+']('+e['license_url']+'), [source]('+e['source_url']+').' for e in entries)+'\n',encoding='utf8')
    report={'commit':args.commit,'before':before,'added':len(added),'total':len(entries),'duplicates_skipped':duplicates,
            'added_ids':[e['asset_id'] for e in added],'rejected':rejected}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rejected','added_ids')}),flush=True)


if __name__=='__main__':main()
