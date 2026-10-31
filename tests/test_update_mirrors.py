import base64, hashlib, json, time, zipfile
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import update_mirrors
from app_updates import UpdateManager
from github_delivery import Cancelled, DeliveryError


def wait(manager):
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        s=manager.status()
        if s['state'] not in ('checking','downloading','validating'):return s
        time.sleep(.01)
    raise AssertionError(manager.status())

@pytest.fixture
def signed(tmp_path,monkeypatch):
    key=Ed25519PrivateKey.generate()
    monkeypatch.setattr(update_mirrors,'PUBLIC_KEY',key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw))
    archive=tmp_path/'app.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('Rylume/Rylume.exe',b'MZfixture')
        z.writestr('Rylume/_internal/python313.dll','fixture')
        z.writestr('Rylume/_internal/ui/canvas-studio.html','fixture')
    data=archive.read_bytes();v='9.0.0';name=f'Rylume-{v}-Windows-x64.zip'
    manifest=json.dumps({'tag_name':'v'+v,'assets':[{'name':name,'size':len(data),'digest':'sha256:'+hashlib.sha256(data).hexdigest(),'browser_download_url':f'https://github.com/zhao060206/Rylume/releases/download/v{v}/{name}'}]}).encode()
    return archive,manifest,base64.b64encode(key.sign(manifest))

class Offline:
    def read(self,*a,**k):raise OSError('offline')
    def download(self,*a,**k):raise OSError('offline')

class Mirror:
    def __init__(self,archive,manifest,signature):self.archive,self.manifest,self.signature=archive,manifest,signature;self.calls=0
    def read(self,url,**kw):return self.signature if url.endswith('.sig') else self.manifest
    def download(self,url,dest,digest,**kw):
        self.calls+=1
        if kw['cancel'].is_set():raise Cancelled('cancelled')
        data=self.archive.read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise DeliveryError('SHA-256 mismatch')
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);return dest

def test_signed_mirror_and_download_fallback(tmp_path,signed):
    mirror=Mirror(*signed);m=UpdateManager(tmp_path/'data',current_version='4.2.0',delivery=Offline());m.mirror_factory=lambda _:mirror
    m.check();s=wait(m);assert s['state']=='available' and '签名已验证' in s['message']
    m.download();s=wait(m);assert s['state']=='ready' and mirror.calls==1

def test_tampered_or_unsigned_mirror_fails_closed(tmp_path,signed):
    archive,manifest,signature=signed
    for raw,sig in ((manifest+b' ',signature),(manifest,b'')):
        mirror=Mirror(archive,raw,sig);m=UpdateManager(tmp_path/str(len(sig)),current_version='4.2.0',delivery=Offline());m.mirror_factory=lambda _:mirror
        m.check();assert wait(m)['state']=='failed' and m.release is None

def test_mirror_cannot_offer_downgrade(tmp_path,signed):
    mirror=Mirror(*signed);m=UpdateManager(tmp_path/'data',current_version='10.0.0',delivery=Offline());m.mirror_factory=lambda _:mirror
    m.check();assert wait(m)['state']=='up_to_date' and m.release is None

def test_invalid_signature_and_mirror_origin(signed):
    _,raw,sig=signed;update_mirrors.verify_manifest(raw,sig)
    with pytest.raises(DeliveryError):update_mirrors.verify_manifest(raw+b' ',sig)
    with pytest.raises(DeliveryError):update_mirrors.MirrorDelivery('https://evil.example/')
