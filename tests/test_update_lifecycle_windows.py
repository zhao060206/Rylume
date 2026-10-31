"""Run the shipped PowerShell helper against real Windows processes and folders."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

pytestmark=pytest.mark.skipif(sys.platform!='win32',reason='Windows update helper')
HELPER=Path(__file__).resolve().parents[1]/'packaging/update-helper.ps1'


@pytest.fixture(scope='module')
def fixture_exe(tmp_path_factory):
    root=tmp_path_factory.mktemp('update-process')
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    source=root/'Fixture.cs'
    source.write_text(r'''
using System;
using System.IO;
using System.Threading;
using System.Collections.Generic;
using System.Web.Script.Serialization;
class Fixture {
    static int Main(string[] args) {
        var folder=AppDomain.CurrentDomain.BaseDirectory;
        string plan=null, nonce=null, marker=null;
        for(int i=0;i+1<args.Length;i++) {
            if(args[i]=="--update-plan") plan=args[++i];
            else if(args[i]=="--update-nonce") nonce=args[++i];
            else if(args[i]=="--marker") marker=args[++i];
        }
        if(marker!=null) File.WriteAllText(marker,File.ReadAllText(Path.Combine(folder,"version.txt")));
        if(plan!=null) {
            if(File.Exists(Path.Combine(folder,"reject-health"))) return 7;
            var json=new JavaScriptSerializer();
            var p=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(plan));
            File.WriteAllText((string)p["health_file"],json.Serialize(new {version=(string)p["version"],nonce=nonce,pid=System.Diagnostics.Process.GetCurrentProcess().Id}));
        }
        for(int i=0;i<600;i++) {
            if(File.Exists(Path.Combine(folder,"stop"))) return 0;
            Thread.Sleep(100);
        }
        return 0;
    }
}''',encoding='utf8')
    exe=root/'Rylume.exe'
    subprocess.run([str(compiler),'/nologo','/target:winexe','/reference:System.Web.Extensions.dll',f'/out:{exe}',str(source)],check=True,capture_output=True)
    return exe


def wait_file(file,timeout=20):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if file.is_file():return
        time.sleep(.05)
    raise AssertionError('Missing lifecycle evidence: '+str(file))


@pytest.mark.parametrize('reject_health',[False,True],ids=['upgrade','rollback'])
def test_update_leaves_inherited_install_cwd_and_preserves_data(tmp_path,fixture_exe,reject_health):
    # Spaces and Chinese also exercise the helper's Windows argument quoting.
    root=tmp_path/'科研 update'
    target=root/'portable/Rylume';target.mkdir(parents=True)
    data=root/'user data';data.mkdir()
    (data/'author-document.json').write_text('{"revision":9}',encoding='utf8')
    (target/'Rylume.exe').write_bytes(fixture_exe.read_bytes())
    (target/'version.txt').write_text('4.5.0')
    stage=data/'updates/staged/package/Rylume';stage.mkdir(parents=True)
    (stage/'Rylume.exe').write_bytes(fixture_exe.read_bytes())
    (stage/'version.txt').write_text('4.5.1')
    if reject_health:(stage/'reject-health').touch()
    nonce=uuid.uuid4().hex;work=data/'updates/apply'/nonce;work.mkdir(parents=True)
    marker=data/'latest launch.txt'
    old=subprocess.Popen([str(target/'Rylume.exe'),'--marker',str(marker)],cwd=target)
    backup=target.with_name(target.name+'.previous-'+nonce)
    plan={'schema_version':1,'parent_pid':old.pid,'install_dir':str(target),'staged_dir':str(stage),
          'data_dir':str(data),'backup_dir':str(backup),'new_dir':str(target.with_name(target.name+'.next-'+nonce)),
          'health_file':str(work/'healthy.json'),'log_file':str(work/'update.log'),
          'version':'4.5.1','nonce':nonce,'args':['--marker',str(marker)],'health_timeout':5}
    planfile=work/'plan.json';planfile.write_text(json.dumps(plan),encoding='utf8')
    ps=Path(os.environ['WINDIR'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    worker=None
    try:
        wait_file(marker)
        # Deliberately inherit the broken old client's cwd. The script must
        # repair its own cwd even when its launcher has not yet been upgraded.
        worker=subprocess.Popen([str(ps),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(HELPER),'-PlanPath',str(planfile)],cwd=target,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        wait_file(work/'update.log')
        (target/'stop').touch();old.wait(timeout=10)
        # The stop marker belongs to the old installation, not the new one.
        stdout,stderr=worker.communicate(timeout=30)
        result=json.loads((work/'result.json').read_text(encoding='utf-8-sig'))
        if reject_health:
            assert worker.returncode==1,(stdout,stderr)
            assert result['state']=='rolled_back' and result['version']=='4.5.1'
            assert (target/'version.txt').read_text()=='4.5.0'
            assert target.with_name(target.name+'.failed-'+nonce).is_dir()
        else:
            assert worker.returncode==0,(stdout,stderr)
            assert result['state']=='completed' and result['version']=='4.5.1'
            assert (target/'version.txt').read_text()=='4.5.1'
            assert (backup/'version.txt').read_text()=='4.5.0'
            assert marker.read_text()=='4.5.1'
            assert not stage.exists()
        assert (data/'author-document.json').read_text(encoding='utf8')=='{"revision":9}'
    finally:
        if target.exists():(target/'stop').touch()
        if old.poll() is None:old.kill();old.wait()
        if worker and worker.poll() is None:worker.kill();worker.wait()
        # Only the fixture process ID written by this isolated test may be killed.
        health=work/'healthy.json'
        if health.exists():
            pid=json.loads(health.read_text())['pid']
            import ctypes
            handle=ctypes.windll.kernel32.OpenProcess(1,False,pid)
            if handle:ctypes.windll.kernel32.TerminateProcess(handle,0);ctypes.windll.kernel32.CloseHandle(handle)
