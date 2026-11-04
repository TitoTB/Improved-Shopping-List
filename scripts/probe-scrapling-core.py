"""Disposable official Core container diagnostic, no integration or user data."""
import asyncio
import importlib.metadata as meta
import inspect
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OUT = Path('/results')
OUT.mkdir(exist_ok=True)
result = {'python':sys.version, 'platform':platform.platform(), 'architecture':platform.machine(), 'stages':{}}

def save():
    (OUT/'result.json').write_text(json.dumps(result,indent=2,default=str))

def command(name, args):
    print('STAGE',name,flush=True)
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=300)
    (OUT/(name+'.txt')).write_text(p.stdout)
    result['stages'][name]={'returncode':p.returncode,'tail':p.stdout[-4500:]}
    save()
    print(name,p.returncode,p.stdout[-1800:],flush=True)
    return p.returncode == 0

import homeassistant
from homeassistant import const
from homeassistant.util import package
result['core']=const.__version__
result['package_installer_signature']=str(inspect.signature(package.install_package))
constraints=getattr(package,'CONSTRAINT_FILE',None)
if not constraints:
    for candidate in (Path(homeassistant.__file__).parent/'package_constraints.txt',Path('/usr/src/homeassistant/package_constraints.txt')):
        if candidate.is_file():constraints=candidate;break
result['constraints']=str(constraints)
result['installed_before']={k:meta.version(k) for k in ('homeassistant','aiohttp','cffi','certifi','lxml','anyio','orjson') if meta.packages_distributions().get(k.replace('-','_'))}
save()
uv=shutil.which('uv')
pip=[uv,'pip'] if uv else [sys.executable,'-m','pip']
common=['--system','--index-strategy','unsafe-first-match'] if uv else ['--break-system-packages']
constraint_args=['--constraint',str(constraints)] if constraints and Path(constraints).is_file() else []
command('baseline_dependencies',pip+['check'])
command('standard_scrapling_plan',pip+['install']+common+['--dry-run']+constraint_args+['scrapling[fetchers]==0.5'])
minimal=['scrapling==0.5','curl_cffi==0.17.0','browserforge==1.2.4','msgspec>=0.21.1','protego>=0.6.2']
minimal_ok=command('minimal_scrapling_plan',pip+['install']+common+['--dry-run']+constraint_args+minimal)
curl_ok=command('curl_install',pip+['install']+common+constraint_args+['curl_cffi==0.17.0'])

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body=json.dumps({'ean':'8410199023094','price':2.89,'content':170,'unit':'g'}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
url='http://127.0.0.1:'+str(server.server_port)+'/product'

async def runtime_check():
    from homeassistant.core import HomeAssistant
    from curl_cffi.requests import AsyncSession, Session
    with tempfile.TemporaryDirectory() as config:
        hass=HomeAssistant(config)
        ticks=0
        async def heartbeat():
            nonlocal ticks
            for _ in range(20):
                await asyncio.sleep(0.01);ticks+=1
        async def query():
            async with AsyncSession(impersonate='chrome') as session:
                response=await session.get(url,timeout=10)
                assert response.status_code==200
                assert response.json()['ean']=='8410199023094'
                return response.json()
        value,_=await asyncio.gather(query(),heartbeat())
        def sync_query():
            with Session(impersonate='chrome') as session:
                return session.get(url,timeout=10).json()
        executor=await hass.async_add_executor_job(sync_query)
        assert executor==value
        await hass.async_block_till_done()
        return {'async_request':value,'executor_request':executor,'event_loop_ticks':ticks,'imported_browser_packages':[m for m in ('playwright','patchright') if m in sys.modules]}

if curl_ok:
    try:
        result['core_package_helper']=package.install_package('curl_cffi==0.17.0',constraints=str(constraints) if constraints else None)
        result['curl_runtime']=asyncio.run(runtime_check())
        result['curl_version']=meta.version('curl_cffi')
    except Exception as err:
        result['curl_runtime_error']=repr(err)
    save()
    command('after_curl_dependencies',pip+['check'])

if minimal_ok and command('minimal_scrapling_install',pip+['install']+common+constraint_args+minimal):
    try:
        from scrapling.fetchers import FetcherSession
        with FetcherSession(impersonate='chrome',retries=1,timeout=10) as session:
            response=session.get(url)
            assert response.status==200
            result['scrapling_runtime']={'status':response.status,'data':response.json()}
    except Exception as err:result['scrapling_runtime_error']=repr(err)
    save()
    command('after_scrapling_dependencies',pip+['check'])
server.shutdown()
result['finished']=True
save()
print('RESULT',json.dumps(result,default=str),flush=True)
