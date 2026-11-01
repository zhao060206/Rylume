"""Build a source-matched palette; never substitute a vaguely related drawing.

Unknown names and former hash-selected assets remain addressable for old scenes
but are quarantined from insertion/search. Collection directories are explicit
inputs; there is no network, model translation or random artwork fallback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from resource_packs import safe_svg
from online_asset_sources import _sanitise

TERMS = {**json.loads((ROOT/'tools/scientific_asset_terms.json').read_text(encoding='utf8')),
         **json.loads((ROOT/'assets/asset-name-terms-zh.json').read_text(encoding='utf8'))}
TERMS.update({'endoplasmic reticulum': '内质网', 'endoplasmatic reticulum': '内质网',
              'cardiac myocytes': '心肌细胞', 'cardiomyocyte': '心肌细胞', 'myocytes': '肌细胞',
              'redbloodcell': '红细胞', 'cell group': '细胞群', 'neonatal': '新生',
              'red blood cell':'红细胞','empty cell':'空白细胞','crispr':'基因编辑系统','cas9':'相关核酸酶9',
              't lymphocyte': '胸腺来源淋巴细胞', 'b lymphocyte': '骨髓来源淋巴细胞',
              'cell complete': '完整细胞', 'cell membrane': '细胞膜', 'dna double stranded ribbon': '脱氧核糖核酸双螺旋带',
              'pink transporter': '粉色转运蛋白', 't cell receptor': '胸腺来源淋巴细胞受体'})
TERMS.update({'with':'含','from':'来自','column':'柱','fruit':'果','fly':'蝇','ul':'微升','moss':'苔藓','gametophore':'配子体',
 'excess':'过量','weight':'重量','naked':'裸露','clothed':'着衣','crosssection':'横截面','colored':'着色','copulation':'交配',
 'icon':'图标','eyed':'眼','wild':'野生型','bench':'工作台','early':'早期','biocondensate':'生物凝聚体','knee':'膝',
 'germlings':'幼体','rice':'水稻','guineapig':'豚鼠','pig':'猪','foam':'泡沫','vldl':'极低密度脂蛋白','counterclockwise':'逆时针',
 'wavy':'波状','arrow3d':'三维箭头','imbalanced':'失衡','traffic':'运输','calculi':'结石','capillaries':'毛细血管',
 'cycle':'循环','color':'颜色','circulation':'循环','rickets':'佝偻病','superficial':'浅表','teeth':'牙齿','hexagon':'六边形',
 'columnar':'柱状','epithel':'上皮','gobelet':'杯状细胞','squamos':'鳞状','gfp':'绿色荧光蛋白','library':'文库',
 'vial':'样品瓶','deep':'深部','roots':'根','burette':'滴定管','stand':'支架','vene':'静脉','tubes':'管',
 'dog':'犬','spotted':'斑点','song':'鸣唱','injection':'注射','nymph':'若虫','mosquito':'蚊','larvae':'幼虫','sun':'太阳',
 'spawning':'产卵','death':'死亡','type':'类型','somite':'体节','elbow':'肘','shoulder':'肩','frontal':'额侧','plane':'平面',
 'ligaments':'韧带','ligament':'韧带','medial':'内侧','through':'穿过','sequencer':'测序仪','conidia':'分生孢子',
 'mycelium':'菌丝体','three':'三','corner':'转角','hot':'高温','closure':'闭合','bile':'胆汁','lithiasis':'结石',
 'pump':'泵','hernia':'疝','bag':'袋','segmentation':'分节','melanoma':'黑色素瘤','mixed':'混合','perfusion':'灌注',
 'pulmonary':'肺部','degree':'角度','burn':'烧伤','ulcer':'溃疡','varicose':'曲张','equipment':'设备',
 'breast':'乳腺','toxoplasma':'弓形虫属','gondii':'刚地弓形虫','cuboid':'立方','pseudostratified':'假复层',
 'bristle':'刚毛','earthmoss':'土生苔藓','calciumsensing':'钙敏感','bluelight':'浅蓝色','lightyellow':'浅黄色'})
# Scientific phrases take precedence over literal word translations. These are
# also applied to collection names copied into another discipline's manifest.
TERMS.update(json.loads((ROOT/'assets/asset-name-phrases-zh.json').read_text(encoding='utf8')))
VISUAL_REVIEW=json.loads((ROOT/'assets/asset-visual-review.json').read_text(encoding='utf8'))
STOP = {'a','an','the','of','and','in','at','for','to','by','on'}
CATEGORIES = {
 'analytical-instrument': ('分析仪器','Analytical instruments'), 'spectroscopy':('光谱与波谱','Spectroscopy'),
 'glassware':('实验玻璃器皿','Laboratory glassware'), 'lab-safety':('实验安全标识','Laboratory safety'),
 'ppe':('个人防护用品','Protective equipment'), 'molecular-modeling':('分子模拟','Molecular modelling'),
 'molecular-structure':('分子结构','Molecular structures'), 'electrochemistry':('电化学','Electrochemistry'),
 'reaction':('反应装置','Reaction apparatus'), 'cultivation':('培养设备','Culture equipment'),
 'mechanics':('力学器材','Mechanics'), 'optics':('光学器材','Optics'), 'electricity':('电路符号','Circuit symbols'),
 'magnetism':('磁学','Magnetism'), 'thermodynamics':('热学','Thermodynamics'), 'waves':('波形','Waveforms'),
 'quantum':('原子与辐射','Atoms and radiation'), 'lab':('实验器材','Laboratory equipment'),
 'mechanical':('机械部件','Mechanical components'), 'manufacturing':('制造设备','Manufacturing equipment'),
 'electrical':('电气设备','Electrical equipment'), 'energy':('能源设备','Energy equipment'),
 'construction':('施工设备','Construction equipment'), 'civil':('土木设施','Civil infrastructure'),
 'fluids':('流体设备','Fluid equipment'), 'robotics':('机器人与传感器','Robotics and sensors'),
 'human':('运输设备','Transport equipment'), 'geology':('地质与地貌','Geology and landforms'),
 'cryosphere':('冰雪','Ice and snow'), 'hydrology':('水文','Hydrology'), 'ocean':('海洋生物与环境','Marine life and environment'),
 'atmosphere':('天气与大气','Weather and atmosphere'), 'ecology':('生态与生物','Ecology and organisms'),
 'field':('野外观测','Field observations'), 'hazards':('自然灾害','Natural hazards'),
 'characterization':('材料表征','Material characterisation'), 'composite':('材料与构件','Materials and components'),
 'crystal-growth':('晶体生长','Crystal growth'), 'crystal-lattice':('晶体与点阵','Crystals and lattices'),
 'crystal-structure':('晶体结构','Crystal structures'), 'defect':('裂纹与缺陷','Cracks and defects'),
 'mechanical-testing':('力学试验','Mechanical testing'), 'nanomaterial':('纳米材料','Nanomaterials'),
 'polymer':('聚合物与弹性体','Polymers and elastomers'), 'thin-film':('表面与薄层','Surfaces and layers'),
 'computing':('计算设备与数据','Computing and data'), 'medicine':('器官与医学器材','Anatomy and medical equipment')
}
MATERIAL_FILES = {'Nanoparticle.svg','Silver_Nanoparticle.svg','hydrophobic-droplet-hydrophilic-surface.svg',
 'hydrophilic-droplet-hydrophobic-surface.svg','crystal-growth.svg','alloy.svg','crystal-cluster.svg',
 'crystal-bars.svg','crystalize.svg','minerals.svg','edge-crack.svg','cracked-glass.svg','atom-core.svg',
 'particles-suspension.svg','particles-solids.svg','spring.svg','metal-plate.svg','concrete-bag.svg',
 'crystal-shine.svg','hexagons.svg','grid-dots.svg','cube.svg','emulsion.svg','particles-foam.svg'}
CORRECT_COLLECTION_NAMES = {
 'crystal-shine.svg':('晶体','Crystal'), 'concrete-bag.svg':('混凝土袋','Concrete bag'),
 'spring.svg':('弹簧','Spring'), 'cube.svg':('立方体','Cube'), 'hexagons.svg':('六边形阵列','Hexagon array'),
 'grid-dots.svg':('点阵','Dot grid'), 'diamond.svg':('钻石','Diamond'),
 'building-broadcast-tower.svg':('广播塔','Broadcast tower'), 'ruler-measure.svg':('测量尺','Measuring ruler'),
 'ph-meter.svg':('酸碱度计','pH meter'), 'DNA.svg':('脱氧核糖核酸双螺旋','DNA double helix'),
 'dna.svg':('脱氧核糖核酸双螺旋','DNA double helix'), 'axis-x.svg':('横坐标轴','Horizontal axis'),
 'axis-y.svg':('纵坐标轴','Vertical axis'), 'axis-3d.svg':('三维坐标轴','Three-dimensional axes'),
 'PCR_cycle.svg':('聚合酶链式反应仪','Thermal cycler'), 'Morse-potential.svg':('莫尔斯势','Morse potential'),
 'qmmm.svg':('量子力学与分子力学混合模型','QM/MM hybrid model'),
 'NFPA-diamond.svg':('美国消防协会危险菱形标识','NFPA hazard diamond'),
 'water_ph_24px.svg':('水体酸碱度','Water pH')
}
COMPUTING = {
 'database':'数据库','database-search':'数据库检索','server':'服务器','server-network':'服务器网络',
 'cloud':'云','network':'网络','graph':'图结构','graph-outline':'图结构轮廓','matrix':'矩阵',
 'chip':'芯片','code-array':'代码数组','api':'应用程序接口','router':'路由器','switch':'开关',
 'docker':'容器平台标识','kubernetes':'容器编排平台标识','table':'数据表','filter':'过滤器符号',
 'signal':'信号强度','monitor-dashboard':'监控面板','text-box':'文本框','source-branch':'代码分支',
 'source-branch-check':'分支检查','transit-connection':'线路连接','sigma':'求和符号',
 'chart-bell-curve':'钟形分布曲线','chart-line':'折线图','scatter-plot':'散点图',
 'function':'函数','grid':'网格','map':'地图','vector-square':'矩形顶点','sitemap':'层级图',
 'eye':'眼睛','translate':'翻译符号','message-text':'文字消息','pipe':'管道',
 'lan-connect':'局域网连接','access-point':'无线接入点','vector-curve':'曲线控制点'
}


def source_title(url):
    name = unquote(str(url).split('/')[-1]).removesuffix('.svg')
    name=re.sub(r'([a-z])([A-Z])',r'\1 \2',name).replace('_',' ').replace('-',' ').strip()
    for old,new in [('redbloodcell','red blood cell'),('emptycell','empty cell'),('emtpycell','empty cell')]:name=name.replace(old,new)
    return name


def chinese_title(title):
    anatomy=re.fullmatch(r'(anterior|posterior|lateral|medial) view of (?:the )?(.+)',title,re.I)
    if anatomy:
        body,missing=chinese_title(anatomy[2])
        return body+'（'+{'anterior':'前面观','posterior':'后面观','lateral':'外侧面观','medial':'内侧面观'}[anatomy[1].lower()]+'）',missing
    tokens = re.findall(r'[a-z]+[0-9]+(?:[a-z]+)?|[0-9]+[a-z]+|[a-z]+|[0-9]+',title.lower())
    result = []; unknown = []; i = 0
    while i < len(tokens):
        found = False
        for width in range(min(5,len(tokens)-i),0,-1):
            phrase=' '.join(tokens[i:i+width])
            if phrase in TERMS:
                result.append(TERMS[phrase]);i+=width;found=True;break
        if found:continue
        word=tokens[i];i+=1
        if word in STOP:continue
        if word.isdigit():result.append(word)
        else:unknown.append(word)
    return ' · '.join(dict.fromkeys(result)), unknown


def record(item,zh,en,source_file):
    reviewed=VISUAL_REVIEW.get(source_file,{})
    item.update(label=zh,label_zh=zh,label_en=en,source_file=source_file)
    if reviewed.get('quarantine'):
        item.update(catalog_status='quarantined',catalog_reason=reviewed['quarantine'],source_file=source_file)
        return
    if 'zh' in reviewed:zh,en=reviewed['zh'],reviewed['en']
    item.update(label=zh,label_zh=zh,label_en=en,catalog_status='source-matched',source_file=source_file,
                review_basis='Pinned upstream filename with explicit bilingual naming; no substitute artwork')
    item.pop('catalog_reason',None)
    if reviewed:item['review_basis']='Source artwork contact-sheet comparison and explicit bilingual naming'


def build(collections):
    manifests={p.parent.name:(p,json.loads(p.read_text(encoding='utf8'))) for p in (ROOT/'resource-packs').glob('*/manifest.json')}
    bio_path=ROOT/'assets/bioicons/manifest.json';bio=json.loads(bio_path.read_text(encoding='utf8'))
    unknown=[];new=[];source_names={};declined=[]
    for folder in collections:
        for a in json.loads((folder/'collection.json').read_text(encoding='utf8')):
            url=a.get('source_url','');name=unquote(url.split('/')[-1]);domain=a['domain']
            if domain not in manifests or not url.startswith('https://') or name=='original':continue
            if a['license']=='MIT' and a['author'] in ('OpenMM','Luca Burgio and Iconoir contributors'):continue
            if domain=='materials' and name not in MATERIAL_FILES:continue
            if name=='tank.svg' or (domain=='chemistry' and a['label_zh']=='容量瓶'):continue
            source=folder/a['file']
            if not source.resolve().is_relative_to(folder.resolve()):raise ValueError('Collection path escapes source directory')
            raw=source.read_text(encoding='utf8')
            try:content=_sanitise(raw)
            except ValueError as exc:
                declined.append({'id':a['id'],'reason':str(exc)});continue
            zh,en=CORRECT_COLLECTION_NAMES.get(name,(a['label_zh'],a['label_en']))
            # A Latin source name in a Chinese label is not a translated name.
            for latin,cn in [('DNA','脱氧核糖核酸'),('PID','比例积分微分'),('Morse','莫尔斯'),('NFPA','美国消防协会'),('QM/MM','量子力学与分子力学')]:zh=zh.replace(latin,cn)
            if re.search(r'[A-Za-z]{2,}',zh):
                translated,missing=chinese_title(zh)
                if missing:continue
                zh=translated
            prefix=domain.replace('-','_')+'_verified_'
            aid=prefix+re.sub('[^a-z0-9_]','_',a['id'].lower())[:79-len(prefix)]
            item={k:a.get(k,'') for k in ('author','author_url','license','license_url','source_url','modifications')}
            category,category_en=CATEGORIES.get(a['category'],CATEGORIES['medicine'])
            box=list(map(float,ET.fromstring(content).get('viewBox').split()));ratio=box[2]/box[3]
            item.update(id=aid,asset_id=aid,type='symbol',category=category,category_en=category_en,
                        default_dim=[round(26*min(ratio,1),2),round(26*min(1/ratio,1),2)],
                        file='assets/'+aid+'.svg',keywords=a['keywords'],source_kind='online-open-license',
                        sha256=hashlib.sha256(content.encode()).hexdigest())
            record(item,zh,en,name);new.append((domain,item,content));source_names[url]=(zh,en)
    for item in bio:
        title=source_title(item['source_url']);zh,missing=chinese_title(title)
        if item['source_url'] in source_names:zh,en=source_names[item['source_url']];missing=[]
        else:en=title
        if not missing and zh and re.search('[\u4e00-\u9fff]',zh):record(item,zh,en,unquote(item['source_url'].split('/')[-1]))
        else:
            item['catalog_status']='quarantined';item['catalog_reason']='Chinese source name needs verification'
            unknown.append({'asset_id':item['asset_id'],'source_title':title,'unknown_terms':missing})
    # Former discipline exports used both hash selection and loose icon aliases.
    # Retain their IDs/files only so historical scene snapshots remain readable.
    for domain,(path,manifest) in manifests.items():
        manifest['assets']=[a for a in manifest['assets'] if not a['id'].startswith('verified_') and '_verified_' not in a['id']]
        for a in manifest['assets']:
            a.update(catalog_status='quarantined',catalog_reason='Legacy source-to-label mapping was not verified')
            artwork=path.parent/a['file']
            if b'\r\n' in artwork.read_bytes():artwork.write_text(artwork.read_text(encoding='utf8'),encoding='utf8',newline='\n')
            a['sha256']=hashlib.sha256(artwork.read_bytes()).hexdigest()
        for t in manifest['templates']:t.update(catalog_status='quarantined',catalog_reason='Contains legacy unverified artwork')
        manifest.update(version='3.0.0',min_app_version='4.8.0')
    for domain,item,content in new:
        path,manifest=manifests[domain]
        if any(a['id']==item['id'] for a in manifest['assets']):continue
        (path.parent/item['file']).write_text(content,encoding='utf8',newline='\n');manifest['assets'].append(item)
    mdi=ROOT/'assets/online-sources/mdi'
    path,manifest=manifests['computing-math']
    for name,zh in COMPUTING.items():
        file=mdi/(name+'.svg')
        if not file.is_file():continue
        from online_asset_sources import MDI_BASE,MDI_LICENSE_URL
        content=_sanitise(file.read_text(encoding='utf8'));aid='computing_math_verified_'+name.replace('-','_')
        item=dict(id=aid,asset_id=aid,type='symbol',file='assets/'+aid+'.svg',category='计算设备与数据',category_en='Computing and data',
                  default_dim=[24,24],keywords=[name,zh],author='Pictogrammers / Material Design Icons',author_url='https://pictogrammers.com/',
                  license='Apache-2.0',license_url=MDI_LICENSE_URL,source_url=MDI_BASE+file.name,source_kind='online-open-license',
                  modifications='Original SVG sanitised; geometry retained',sha256=hashlib.sha256(content.encode()).hexdigest())
        record(item,zh,source_title(file.name),file.name);manifest['assets'].append(item);(path.parent/item['file']).write_text(content,encoding='utf8',newline='\n')
    # Medical anatomy uses the same genuine artwork, with a new ID rather than
    # reassigning an unrelated existing medical ID to a different silhouette.
    path,manifest=manifests['medicine']
    for item in bio:
        if item.get('catalog_status')!='source-matched' or not any(part in item['source_url'] for part in ('Human_physiology/','Blood_Immunology/','Lab_apparatus/')):continue
        if len([a for a in manifest['assets'] if a.get('catalog_status')=='source-matched'])>=120:break
        aid='medicine_verified_'+hashlib.sha256(item['source_url'].encode()).hexdigest()[:16]
        content=(ROOT/'ui/library'/(item['asset_id']+'.svg')).read_text(encoding='utf8')
        try:content=safe_svg(content)
        except ValueError:continue
        a={**item,'id':aid,'asset_id':aid,'file':'assets/'+aid+'.svg','type':'symbol','category':'器官与医学器材','category_en':'Anatomy and medical equipment',
           'sha256':hashlib.sha256(content.encode()).hexdigest(),'source_kind':'online-open-license'}
        a.pop('thumbnail',None);a.pop('domain',None);manifest['assets'].append(a);(path.parent/a['file']).write_text(content,encoding='utf8',newline='\n')
    bio_path.write_text(json.dumps(bio,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    counts={}
    for domain,(path,manifest) in manifests.items():
        manifest['available_asset_count']=sum(a.get('catalog_status')=='source-matched' for a in manifest['assets'])
        manifest['available_template_count']=0
        path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        counts[domain]={'available':manifest['available_asset_count'],'quarantined':len(manifest['assets'])-manifest['available_asset_count']}
    review={a['asset_id']:{k:a[k] for k in ('label','label_zh','label_en','category_en','catalog_status','catalog_reason','review_basis','source_url') if k in a}
            for a in bio+[a for _,m in manifests.values() for a in m['assets']]}
    (ROOT/'assets/asset-catalog-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    sources={a['id']:{'file':str((path.parent/a['file']).relative_to(ROOT)).replace('\\','/'),
                      **{k:a[k] for k in ('author','license','license_url','source_url','source_file','source_kind','modifications')}}
             for path,m in manifests.values() for a in m['assets'] if a.get('catalog_status')=='source-matched'}
    sources['balance']=sources['chemistry_verified_chem_analytical_balance']
    (ROOT/'assets/online-sources/verified-source-mapping.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    report={'biology_source_matched':sum(a.get('catalog_status')=='source-matched' for a in bio),
            'biology_quarantined':sum(a.get('catalog_status')=='quarantined' for a in bio),'packs':counts,'untranslated_source_names':unknown,'rejected_imports':declined,
            'review_scope':'Source-title identity and controlled bilingual metadata; contact-sheet review is recorded separately'}
    (ROOT/'assets/asset-catalog-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='untranslated_source_names'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--collection',type=Path,action='append',default=[])
    build(parser.parse_args().collection)
