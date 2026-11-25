"""Authenticated update metadata and constrained third-party mirror transport."""
from __future__ import annotations
import base64
from urllib.parse import urljoin, urlparse
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from github_delivery import GitHubDelivery, DeliveryError, REPOSITORY, trusted_url

# Rotated in 5.0.0 (the previous signing key was lost; 4.12.x clients on a mirror must install 5.0.0 once).
PUBLIC_KEY = bytes.fromhex('0cfc5afd5563cffa14644d703e1254a106340fd6ca45ec30515b5aa550f8b910')
MIRRORS = ('https://ghfast.top/', 'https://ghproxy.net/')

def verify_manifest(data, signature):
    try:
        raw=base64.b64decode(signature.strip(),validate=True)
        Ed25519PublicKey.from_public_bytes(PUBLIC_KEY).verify(raw,data)
    except (ValueError,InvalidSignature,TypeError):
        raise DeliveryError('备用线路的更新签名无效，已拒绝更新') from None

class MirrorDelivery(GitHubDelivery):
    def __init__(self, prefix, session=None):
        if prefix not in MIRRORS:raise DeliveryError('未知备用线路')
        super().__init__(session);self.prefix=prefix
    def response(self,url,stream=False):
        trusted_url(url)
        if not url.startswith('https://github.com/'+REPOSITORY+'/releases/'):
            raise DeliveryError('备用线路仅支持官方发布文件')
        url=self.prefix+url
        for _ in range(6):
            parsed=urlparse(url)
            if parsed.hostname in {urlparse(p).hostname for p in MIRRORS}:
                if not url.startswith(self.prefix+'https://github.com/'+REPOSITORY+'/releases/') or parsed.username or parsed.password or parsed.fragment:
                    raise DeliveryError('备用线路返回了不受信任的地址')
            else:trusted_url(url)
            response=self.session.get(url,timeout=(8,20),stream=stream,allow_redirects=False,headers={'User-Agent':'Rylume-Public-Delivery','Accept':'*/*'})
            if response.status_code in (301,302,303,307,308):
                next_url=urljoin(url,response.headers.get('Location',''));response.close();url=next_url;continue
            if response.status_code!=200:
                code=response.status_code;response.close();raise DeliveryError('备用线路请求未完成（HTTP '+str(code)+'）')
            return response
        raise DeliveryError('备用线路重定向次数过多')
