"""Create public update metadata from a completed Windows ZIP (never from config)."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from product_identity import PRODUCT_VERSION
from github_delivery import version_tuple,REPOSITORY

def prepare(archive,output,version=PRODUCT_VERSION,notes=''):
    version_tuple(version);archive=Path(archive);output=Path(output)
    expected=f'Rylume-{version}-Windows-x64.zip'
    if archive.name!=expected:raise ValueError('Archive name must be '+expected)
    with archive.open('rb') as handle:sha=hashlib.file_digest(handle,'sha256').hexdigest()
    url=f'https://github.com/{REPOSITORY}/releases/download/v{version}/{archive.name}'
    manifest={'tag_name':'v'+version,'draft':False,'prerelease':False,'body':notes,
        'assets':[{'name':archive.name,'size':archive.stat().st_size,'digest':'sha256:'+sha,'browser_download_url':url}]}
    output.mkdir(parents=True,exist_ok=True)
    (output/'update.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    (output/'SHA256SUMS.txt').write_text(sha+'  '+archive.name+'\n',encoding='ascii')
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--output',required=True);p.add_argument('--version',default=PRODUCT_VERSION);p.add_argument('--notes-file');a=p.parse_args()
    prepare(a.archive,a.output,a.version,Path(a.notes_file).read_text(encoding='utf8') if a.notes_file else '')
