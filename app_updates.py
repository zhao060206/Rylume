"""Explicit, keyless GitHub updates for the Windows portable distribution."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import uuid
from github_delivery import GitHubDelivery,DeliveryError,Cancelled,checked_zip,version_tuple,REPOSITORY,trusted_url
from resource_packs import _write
from product_identity import PRODUCT_VERSION

class UpdateManager:
    def __init__(self,data_dir,install_dir=None,current_version=PRODUCT_VERSION,delivery=None,frozen=None,launcher=None):
        self.data_dir=Path(data_dir).resolve();self.root=self.data_dir/'updates'
        self.install_dir=Path(install_dir or Path(sys.executable).parent).resolve()
        self.current=current_version;self.delivery=delivery or GitHubDelivery();self.lock=threading.RLock()
        self.frozen=bool(getattr(sys,'frozen',False)) if frozen is None else frozen
        self.launcher=launcher or subprocess.Popen;self.cancel_event=threading.Event();self.release=None;self.stage=None
        self.info={'state':'idle','current_version':self.current,'latest_version':None,'progress':0,'error':'','can_apply':False}
    def status(self):
        with self.lock:return {'ok':True,**copy.deepcopy(self.info)}
    def _set(self,**kwargs):
        with self.lock:self.info.update(kwargs)
    def check(self):
        with self.lock:
            if self.info['state'] in ('checking','downloading','validating','ready','installing'):return self.status()
            self._set(state='checking',error='')
        def work():
            try:
                try:d=json.loads(self.delivery.read(f'https://github.com/{REPOSITORY}/releases/latest/download/update.json',limit=128*1024))
                except Exception:d=json.loads(self.delivery.read(f'https://api.github.com/repos/{REPOSITORY}/releases/latest'))
                version=d.get('tag_name','').removeprefix('v');new=version_tuple(version)>version_tuple(self.current)
                if d.get('draft') or d.get('prerelease'):raise DeliveryError('此版本不是正式发行版')
                if not new:self._set(state='up_to_date',latest_version=version);return
                name=f'Rylume-{version}-Windows-x64.zip'
                asset=next((a for a in d.get('assets',[]) if a.get('name')==name),None)
                if not asset or not isinstance(asset.get('size'),int) or not 0<asset['size']<1024**3:raise DeliveryError('最新版缺少完整 Windows 安装包')
                url=asset['browser_download_url'];trusted_url(url)
                if not url.startswith(f'https://github.com/{REPOSITORY}/releases/download/v{version}/'):raise DeliveryError('安装包不属于此版本')
                digest=asset.get('digest','')
                if not re.fullmatch('sha256:[0-9a-f]{64}',digest):
                    checksum=next((a for a in d['assets'] if a['name']=='SHA256SUMS.txt'),None)
                    if not checksum:raise DeliveryError('此版本没有 SHA-256 校验文件')
                    text=self.delivery.read(checksum['browser_download_url'],limit=16384).decode()
                    matches=[line.split()[0] for line in text.splitlines() if len(line.split())==2 and line.split()[1]==name]
                    if len(matches)!=1 or not re.fullmatch('[0-9a-f]{64}',matches[0]):raise DeliveryError('安装包校验记录无效')
                    digest='sha256:'+matches[0]
                self.release={'version':version,'asset':asset,'sha256':digest[7:]}
                self._set(state='available',latest_version=version,notes=str(d.get('body',''))[:8000],
                    release_url=f'https://github.com/{REPOSITORY}/releases/tag/v{version}',total=asset['size'])
            except Exception as exc:self._set(state='failed',error=str(exc) if isinstance(exc,DeliveryError) else '暂时无法检查 GitHub 更新，可以稍后重试')
        threading.Thread(target=work,daemon=True,name='update-check').start();return self.status()
    def download(self):
        with self.lock:
            if self.info['state'] in ('downloading','validating','ready','installing'):return self.status()
            if not self.release:raise DeliveryError('请先检查并找到新版本')
            self.cancel_event=threading.Event();self._set(state='downloading',progress=0,error='')
        def work():
            stage=self.root/'staged'/uuid.uuid4().hex
            try:
                release=self.release;asset=release['asset'];file=self.root/'downloads'/asset['name']
                self.delivery.download(asset['browser_download_url'],file,release['sha256'],limit=1024**3,total=asset['size'],cancel=self.cancel_event,
                    progress=lambda n,t:self._set(downloaded=n,total=t,progress=round(n/max(1,t)*85,1)))
                self._set(state='validating',progress=88)
                checked_zip(file,stage)
                candidate=stage/'Rylume'
                if not (candidate/'Rylume.exe').is_file() or not (candidate/'_internal/python313.dll').is_file() or not (candidate/'_internal/ui/canvas-studio.html').is_file():raise DeliveryError('下载包缺少完整的 Rylume 程序文件')
                forbidden={'config.json','config.local.json','local-key.txt','studio-jobs','exports','webview-profile'}
                if any(p.name.lower() in forbidden for p in candidate.rglob('*')):raise DeliveryError('安装包混入本机配置或任务，已拒绝更新')
                if self.cancel_event.is_set():raise Cancelled('更新下载已取消')
                self.stage=candidate
                can_apply=self.frozen and sys.platform=='win32' and os.access(self.install_dir,os.W_OK)
                self._set(state='ready',progress=100,can_apply=can_apply,
                    message='下载和校验完成，保存图版后可重启更新' if can_apply else '安装包已校验；源码运行或此目录不可写，请从发布页解压安装',download_path=str(file))
            except Cancelled:self._set(state='cancelled',error='下载已取消，当前版本继续可用')
            except Exception as exc:self._set(state='failed',error=str(exc) if isinstance(exc,DeliveryError) else '更新下载未完成，请重试；当前版本保持可用')
            finally:
                if self.stage is None and stage.exists() and stage.resolve().is_relative_to((self.root/'staged').resolve()):shutil.rmtree(stage)
        self.stage=None
        threading.Thread(target=work,daemon=True,name='update-download').start();return self.status()
    def cancel(self):self.cancel_event.set();return self.status()
    def apply(self,restart_args=None,helper=None):
        if not self.frozen or sys.platform!='win32':raise DeliveryError('自动替换仅支持 Windows 打包版；源码版请自行更新源码')
        if self.info['state']!='ready' or not self.stage:raise DeliveryError('请先完成下载和校验')
        target=self.install_dir.resolve();data=self.data_dir.resolve();stage=self.stage.resolve()
        system=Path(os.environ.get('WINDIR',r'C:\Windows')).resolve()
        if target==Path(target.anchor) or target.is_relative_to(system) or data==target or data.is_relative_to(target) or target.is_relative_to(data) or len(target.parts)<3:
            raise DeliveryError('安装目录与系统或用户数据重叠，不能自动替换')
        if not (target/'Rylume.exe').is_file() or not os.access(target,os.W_OK):raise DeliveryError('当前安装目录不可写，请将程序解压到自己的文件夹后更新')
        if not stage.is_relative_to((self.root/'staged').resolve()):raise DeliveryError('更新暂存目录无效')
        args=list(restart_args or [])
        if any(not isinstance(a,str) or '\x00' in a for a in args):raise DeliveryError('重启参数无效')
        nonce=uuid.uuid4().hex;work=self.root/'apply'/nonce;work.mkdir(parents=True)
        helper=Path(helper) if helper else Path(__file__).parent/'packaging/update-helper.ps1'
        script=work/'update-helper.ps1';shutil.copyfile(helper,script)
        plan={'schema_version':1,'parent_pid':os.getpid(),'install_dir':str(target),'staged_dir':str(stage),
            'data_dir':str(data),'backup_dir':str(target.with_name(target.name+'.previous-'+nonce)),
            'new_dir':str(target.with_name(target.name+'.next-'+nonce)),'health_file':str(work/'healthy.json'),
            'log_file':str(work/'update.log'),'version':self.release['version'],'nonce':nonce,'args':args}
        _write(work/'plan.json',plan)
        powershell=str(Path(os.environ.get('SYSTEMROOT',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe')
        self.launcher([powershell,'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',str(script),'-PlanPath',str(work/'plan.json')],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self._set(state='installing',message='正在退出并替换程序；启动失败会恢复旧版')
        return self.status()

def acknowledge(data_dir,plan_path,nonce):
    """Called only after the new HTTP server and native web page are healthy."""
    if not plan_path:return
    root=(Path(data_dir).resolve()/'updates/apply').resolve();path=Path(plan_path).resolve()
    if not path.is_relative_to(root) or path.name!='plan.json':raise DeliveryError('更新确认路径无效')
    p=json.loads(path.read_text(encoding='utf8'))
    if p['nonce']!=nonce or p['version']!=PRODUCT_VERSION:raise DeliveryError('更新确认版本不一致')
    _write(Path(p['health_file']),{'version':PRODUCT_VERSION,'nonce':nonce,'pid':os.getpid()})
