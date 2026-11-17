"""Cambia el repositorio INGEFIX existente a público usando la sesión Git de Windows."""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'github-source'
OWNER='oscarillo12'
NAME='ingefix-logistica'
REMOTE=f'https://github.com/{OWNER}/{NAME}.git'
AUTH_STORE=ROOT/'data'/'github-auth'
RESULT=ROOT/'data'/'publicacion-github.txt'

def run(args,**kwargs):
    if args[0]=='git':
        args=['git','-c','safe.directory='+SOURCE.resolve().as_posix(),'-c','credential.credentialStore=dpapi','-c','credential.dpapiStorePath='+str(AUTH_STORE),*args[1:]]
    return subprocess.run(args,check=True,**kwargs)

def publish():
    remote=run(['git','-C',str(SOURCE),'remote','get-url','origin'],capture_output=True,text=True).stdout.strip()
    if remote!=REMOTE:raise ValueError('El repositorio configurado no coincide con oscarillo12/ingefix-logistica.')
    files=run(['git','-C',str(SOURCE),'ls-files'],capture_output=True,text=True).stdout.splitlines()
    forbidden=[p for p in files if p.startswith('data/') or Path(p).suffix.lower() in ('.pdf','.xlsx','.db','.log','.env') or p.endswith('.local.json')]
    if forbidden:raise ValueError('Se detectaron documentos o archivos operativos versionados; no se cambia la visibilidad.')
    env=dict(os.environ,GCM_INTERACTIVE='never',GIT_TERMINAL_PROMPT='0')
    credential=run(['git','credential','fill'],input=f'protocol=https\nhost=github.com\nusername={OWNER}\n\n',capture_output=True,text=True,env=env)
    token=dict(line.split('=',1) for line in credential.stdout.splitlines() if '=' in line).get('password')
    if not token:raise ValueError('No se encontró una autorización GitHub válida. Ejecuta SUBIR_GITHUB.bat primero.')
    def api(method):
        req=urllib.request.Request(f'https://api.github.com/repos/{OWNER}/{NAME}',data=json.dumps({'private':False}).encode() if method=='PATCH' else None,method=method,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'INGEFIX-publisher'})
        with urllib.request.urlopen(req,timeout=40) as response:return json.load(response)
    user_req=urllib.request.Request('https://api.github.com/user',headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'INGEFIX-publisher'})
    with urllib.request.urlopen(user_req,timeout=40) as response:user=json.load(response)
    if user.get('login','').lower()!=OWNER:raise ValueError('La sesión autenticada no corresponde a oscarillo12.')
    repo=api('GET')
    if repo.get('private'):repo=api('PATCH')
    if repo.get('private'):raise ValueError('GitHub no confirmó el cambio a público.')
    return repo['html_url']

if __name__=='__main__':
    try:
        url=publish();message='REPOSITORIO PÚBLICO VERIFICADO\n'+url+'\n';print(message,flush=True)
    except (ValueError,OSError,subprocess.CalledProcessError,urllib.error.URLError) as e:
        message='CAMBIO A PÚBLICO NO COMPLETADO\n'+str(e)+'\n';print(message,flush=True);sys.exit(1)
    finally:
        RESULT.parent.mkdir(exist_ok=True)
        RESULT.write_text(message,encoding='utf-8')
