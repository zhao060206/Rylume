"""Package checked-in, source-matched assets without generating replacement art."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from resource_packs import safe_svg


def build(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    catalog={'schema_version':1,'packs':[]}
    for path in sorted((ROOT/'resource-packs').glob('*/manifest.json')):
        folder=path.parent;manifest=json.loads(path.read_text(encoding='utf8'))
        for a in manifest['assets']:
            file=(folder/a['file']).resolve()
            if not file.is_relative_to(folder.resolve()):raise ValueError('Asset escapes pack')
            safe_svg(file.read_text(encoding='utf8'))
            if hashlib.sha256(file.read_bytes()).hexdigest()!=a['sha256']:raise ValueError('Asset digest mismatch: '+a['id'])
            if a.get('catalog_status')=='source-matched' and not all(a.get(k) for k in ('label_zh','label_en','source_url','source_file')):raise ValueError('Missing reviewed bilingual source metadata')
        credits=['Open-source artwork. The application does not claim authorship of these images.',
                 'Quarantined legacy files are retained only for historical documents and are not offered in the palette.',
                 'Per-asset attribution, original URLs, modifications and licences follow.\n']
        credits.extend(a['label_en']+' — '+a['author']+'; '+a['license']+'; '+a['license_url']+'; '+a['source_url']+'; '+a.get('modifications','')
                       for a in manifest['assets'])
        for licence in sorted((ROOT/'licenses/artwork').glob('*.txt')):
            credits.extend(['\n'+licence.name+'\n',licence.read_text(encoding='utf8')])
        (folder/'LICENSE.txt').write_text('\n\n'.join(credits).rstrip()+'\n',encoding='utf8')
        filename=f"rylume-pack-{manifest['id']}-{manifest['version']}.zip";destination=output/filename
        with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for file in sorted(folder.rglob('*')):
                if not file.is_file():continue
                info=zipfile.ZipInfo(file.relative_to(folder).as_posix(),date_time=(2026,11,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
                archive.writestr(info,file.read_bytes())
        with zipfile.ZipFile(destination) as archive:
            if archive.testzip() is not None:raise ValueError('Damaged resource archive')
        catalog['packs'].append({k:manifest[k] for k in ('id','version','title','domain','min_app_version','available_asset_count','available_template_count')})
        catalog['packs'][-1].update(description=manifest['title']+' · 已核对的开源素材',asset_count=len(manifest['assets']),
             template_count=len(manifest['templates']),asset_name=filename,sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),size=destination.stat().st_size)
    data=json.dumps(catalog,ensure_ascii=False,indent=2)+'\n'
    (output/'catalog.json').write_text(data,encoding='utf8');(ROOT/'assets/resource-catalog.json').write_text(data,encoding='utf8')
    print(json.dumps({'packs':len(catalog['packs']),'available_assets':sum(p['available_asset_count'] for p in catalog['packs'])}))
    return catalog


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('out/resource-packs'));args=parser.parse_args();build(args.output)
