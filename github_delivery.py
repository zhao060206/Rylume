"""Public GitHub delivery, with bounded downloads and checked ZIP extraction."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
from urllib.parse import urlparse, urljoin,unquote
import zipfile
import requests

REPOSITORY = 'zhao060206/Rylume'
HOSTS = {'github.com','api.github.com','release-assets.githubusercontent.com',
         'objects.githubusercontent.com','raw.githubusercontent.com'}

class DeliveryError(ValueError):pass
class Cancelled(DeliveryError):pass

def version_tuple(value):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',str(value))
    if not match:raise DeliveryError('版本格式无效')
    return tuple(map(int,match.groups()))

def trusted_url(url):
    p=urlparse(str(url))
    if '\\' in unquote(p.path) or '..' in unquote(p.path).split('/') or p.fragment:raise DeliveryError('下载路径无效')
    if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,443):
        raise DeliveryError('下载地址不属于受信任的 GitHub HTTPS 服务')
    if p.hostname=='github.com' and not p.path.startswith('/'+REPOSITORY+'/'):
        raise DeliveryError('下载地址不属于 Rylume 官方仓库')
    if p.hostname=='api.github.com' and not p.path.startswith('/repos/'+REPOSITORY+'/'):
        raise DeliveryError('版本地址不属于 Rylume 官方仓库')
    if p.hostname=='raw.githubusercontent.com' and not p.path.startswith('/'+REPOSITORY+'/'):
        raise DeliveryError('目录地址不属于 Rylume 官方仓库')
    return url

class GitHubDelivery:
    def __init__(self,session=None):
        self.session=session or requests.Session()
    def response(self,url,stream=False):
        for _ in range(6):
            trusted_url(url)
            response=self.session.get(url,timeout=(12,35),stream=stream,allow_redirects=False,
                headers={'User-Agent':'Rylume-Public-Delivery','Accept':'application/vnd.github+json' if urlparse(url).hostname=='api.github.com' else '*/*'})
            if response.status_code in (301,302,303,307,308):
                next_url=urljoin(url,response.headers.get('Location',''));response.close();url=next_url;continue
            if response.status_code!=200:
                code=response.status_code;response.close()
                raise DeliveryError('GitHub 请求未完成（HTTP '+str(code)+'），可以稍后重试')
            return response
        raise DeliveryError('GitHub 下载重定向次数过多')
    def read(self,url,limit=2*1024*1024):
        with self.response(url,True) as response:
            data=bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data)>limit:raise DeliveryError('远程目录超过允许大小')
            return bytes(data)
    def download(self,url,destination,sha256,*,limit,total=0,cancel=None,progress=None):
        if not re.fullmatch('[0-9a-f]{64}',str(sha256)):raise DeliveryError('缺少有效的 SHA-256 校验值')
        destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_suffix(destination.suffix+'.part');digest=hashlib.sha256();received=0
        try:
            with self.response(url,True) as response,temporary.open('wb') as handle:
                declared=int(response.headers.get('Content-Length') or total or 0)
                if declared>limit:raise DeliveryError('下载文件过大')
                for chunk in response.iter_content(256*1024):
                    if cancel and cancel.is_set():raise Cancelled('下载已取消')
                    if not chunk:continue
                    received+=len(chunk)
                    if received>limit:raise DeliveryError('下载文件过大')
                    handle.write(chunk);digest.update(chunk)
                    if progress:progress(received,declared)
                handle.flush();os.fsync(handle.fileno())
            if cancel and cancel.is_set():raise Cancelled('下载已取消')
            if total and received!=total:raise DeliveryError('文件下载不完整，请重试')
            if digest.hexdigest()!=sha256:raise DeliveryError('文件 SHA-256 不匹配，已停止安装，请重新下载')
            os.replace(temporary,destination)
            return destination
        finally:temporary.unlink(missing_ok=True)

def checked_zip(archive,destination,*,max_files=6000,max_bytes=1500*1024*1024,allowed_suffixes=None):
    """Preflight every entry before extracting anything into a fresh directory."""
    destination=Path(destination).resolve()
    if destination.exists():raise DeliveryError('解压暂存目录必须为空且不存在')
    with zipfile.ZipFile(archive) as z:
        entries=z.infolist();seen=set();total=0;files=set();dirs=set()
        if len(entries)>max_files:raise DeliveryError('资源包文件数量过多')
        for item in entries:
            rawname=item.orig_filename
            path=PurePosixPath(rawname);parts=path.parts
            if not parts or '\x00' in rawname or path.is_absolute() or '\\' in rawname or any(p in ('.','..') or ':' in p or p.rstrip(' .')!=p or re.match(r'(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)',p) for p in parts):
                raise DeliveryError('压缩包包含不安全路径')
            key='/'.join(parts).casefold()
            if key in seen:raise DeliveryError('压缩包包含重复或大小写冲突的文件')
            seen.add(key)
            mode=item.external_attr>>16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR)):
                raise DeliveryError('压缩包不能包含链接或设备文件')
            if item.flag_bits&1:raise DeliveryError('不能安装加密资源包')
            if item.is_dir():dirs.add(key);continue
            files.add(key);dirs.update('/'.join(parts[:n]).casefold() for n in range(1,len(parts)))
            total+=item.file_size
            if total>max_bytes or item.file_size>max_bytes or (item.file_size>16*1024*1024 and item.file_size/max(1,item.compress_size)>500):
                raise DeliveryError('压缩包解压大小超过限制')
            if allowed_suffixes and path.suffix.lower() not in allowed_suffixes:raise DeliveryError('资源包包含不允许的文件类型')
            if not (destination/Path(*parts)).resolve().is_relative_to(destination):raise DeliveryError('压缩包越界')
        if files&dirs:raise DeliveryError('压缩包文件与目录冲突')
        destination.mkdir(parents=True)
        for item in entries:
            target=destination/Path(*PurePosixPath(item.filename).parts)
            if item.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(item) as src,target.open('xb') as dst:
                import shutil
                shutil.copyfileobj(src,dst,256*1024)
    return destination
