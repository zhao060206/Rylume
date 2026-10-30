"""Local HTTP adapter for data packs and application updates."""
import re
import threading
import time
from pathlib import Path
from github_delivery import DeliveryError
from resource_packs import configure,DOMAIN_TITLES
from app_updates import UpdateManager,acknowledge

_updater=None;_lock=threading.RLock()

def updater(app):
    global _updater
    with _lock:
        if _updater is None or _updater.data_dir!=Path(app.DATA_DIR).resolve():
            _updater=UpdateManager(app.DATA_DIR,install_dir=app.BASE_DIR,frozen=app.FROZEN)
        return _updater

def shutdown(app):
    def work():
        time.sleep(.8)
        try:
            import webview
            for window in list(webview.windows):window.destroy()
        except Exception:pass
        if app.SERVER:app.SERVER.shutdown()
    threading.Thread(target=work,daemon=True).start()

def dispatch(handler,method,path,app):
    if not path.startswith(('/api/resources','/api/updates')):return False
    try:
        resources=configure(app.DATA_DIR)
        if path.startswith('/api/resources/file/') and method=='GET':
            match=re.fullmatch(r'/api/resources/file/([a-z][a-z0-9_-]*)/(\d+\.\d+\.\d+)/(.+)',path)
            if not match:raise DeliveryError('资源路径无效')
            pid,version,name=match.groups();installed=resources.installed()
            if installed.get(pid,{}).get('version')!=version:raise DeliveryError('此资源包版本未安装')
            file=resources.file_path(resources.root/'packs'/pid/version,name)
            if file.suffix!='.svg':raise DeliveryError('此资源不提供预览')
            handler._send(200,file.read_bytes(),'image/svg+xml',{'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; sandbox"});return True
        body=handler._body() if method=='POST' else {}
        if path=='/api/resources' and method=='GET':result=resources.status()
        elif path=='/api/resources/refresh' and method=='POST':result=resources.refresh()
        elif path=='/api/resources/install' and method=='POST':result=resources.install(str(body.get('id','')))
        elif path=='/api/resources/cancel' and method=='POST':result=resources.cancel(str(body.get('id','')))
        elif path=='/api/resources/uninstall' and method=='POST':result=resources.uninstall(str(body.get('id','')))
        elif path=='/api/updates' and method=='GET':result=updater(app).status()
        elif path=='/api/updates/check' and method=='POST':result=updater(app).check()
        elif path=='/api/updates/download' and method=='POST':result=updater(app).download()
        elif path=='/api/updates/cancel' and method=='POST':result=updater(app).cancel()
        elif path=='/api/updates/health' and method=='POST':
            acknowledge(app.DATA_DIR,getattr(app,'UPDATE_PLAN',None),getattr(app,'UPDATE_NONCE',None));result={'ok':True}
        elif path=='/api/updates/apply' and method=='POST':
            import annotation_service
            if annotation_service._ACTIVE:raise DeliveryError('请先等待或取消批注修改任务，再重启更新')
            with app.JOBS_LOCK:
                if any(j.get('status') in ('queued','running','processing') or (j.get('ppt_export') or {}).get('state')=='running' for j in app.JOBS.values()):raise DeliveryError('请先等待生成或导出任务完成，再重启更新')
            if any(t.get('state') in ('queued','downloading','validating','installing') for t in resources.tasks.values()):raise DeliveryError('请先完成或取消素材下载，再重启更新')
            helper=Path(__file__).parent/'packaging/update-helper.ps1'
            result=updater(app).apply(getattr(app,'RESTART_ARGS',[]),helper=helper)
            handler._json(200,result);shutdown(app);return True
        else:
            handler._json(404,{'ok':False,'error':'接口不存在'});return True
        handler._json(200,result)
    except (ValueError,OSError,KeyError) as exc:handler._json(400,{'ok':False,'error':str(exc)[:250]})
    return True
