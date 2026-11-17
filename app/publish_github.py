"""Publicación explícita desde Windows: OAuth de Git, API privada y push.

Ejecutar fuera del entorno restringido del agente. Tokens solo en memoria y en
el administrador de credenciales de Git; nunca argumentos, archivos ni salida.
"""
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

def run(args,**kwargs):
    return subprocess.run(args,check=True,**kwargs)

def main():
    env=dict(os.environ)
    for key in ('GIT_TRACE','GIT_TRACE_CURL','GIT_CURL_VERBOSE','GCM_TRACE','GIT_TRACE_PACKET'):env.pop(key,None)
    if not (SOURCE/'.git').is_dir():raise ValueError('No se encuentra el repositorio preparado en github-source.')
    result=run(['git','-C',str(SOURCE),'status','--porcelain'],capture_output=True,text=True,env=env)
    if result.stdout.strip():raise ValueError('Hay cambios sin confirmar en github-source. Deben revisarse antes de publicar.')
    files=run(['git','-C',str(SOURCE),'ls-files'],capture_output=True,text=True,env=env).stdout.splitlines()
    forbidden=[p for p in files if p.startswith('data/') or Path(p).suffix.lower() in ('.pdf','.xlsx','.db','.log','.env') or p.endswith('.local.json')]
    if forbidden:raise ValueError('Se detectaron archivos operativos en la selección. Se detiene la publicación para revisarlos.')
    print('Autoriza GitHub en el navegador con la cuenta oscarillo12.',flush=True)
    run(['git','credential-manager','github','login','--username',OWNER,'--browser'],env=env)
    env['GCM_INTERACTIVE']='never';env['GIT_TERMINAL_PROMPT']='0'
    credential=run(['git','credential','fill'],input=f'protocol=https\nhost=github.com\nusername={OWNER}\n\n',capture_output=True,text=True,env=env)
    values=dict(line.split('=',1) for line in credential.stdout.splitlines() if '=' in line)
    token=values.get('password')
    if not token:raise ValueError('Git no devolvió una autorización utilizable. No se ha subido el código.')
    def api(path,body=None):
        request=urllib.request.Request('https://api.github.com'+path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'INGEFIX-publisher','Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=45) as response:return json.load(response)
    user=api('/user')
    if user.get('login','').lower()!=OWNER.lower():raise ValueError('La cuenta autenticada no es oscarillo12. No se publica en otra cuenta.')
    try:repository=api(f'/repos/{OWNER}/{NAME}')
    except urllib.error.HTTPError as error:
        if error.code!=404:raise
        repository=api('/user/repos',dict(name=NAME,private=True,description='Control logístico INGEFIX: inventario, conteo cíclico y reposición',auto_init=False))
    if not repository.get('private'):raise ValueError('El repositorio existente es público. Se detiene la publicación; no se cambia su visibilidad automáticamente.')
    remote=run(['git','-C',str(SOURCE),'remote','get-url','origin'],capture_output=True,text=True,env=env).stdout.strip()
    if remote!=REMOTE:raise ValueError('El destino origin no coincide con el repositorio previsto.')
    run(['git','-C',str(SOURCE),'push','-u','origin','main'],env=env)
    local=run(['git','-C',str(SOURCE),'rev-parse','HEAD'],capture_output=True,text=True,env=env).stdout.strip()
    published=run(['git','-C',str(SOURCE),'ls-remote','origin','refs/heads/main'],capture_output=True,text=True,env=env).stdout.split()
    if not published or published[0]!=local:raise ValueError('No se pudo verificar que GitHub tenga el último commit.')
    print('\nPUBLICACIÓN VERIFICADA: '+repository['html_url'],flush=True)
    print('Repositorio privado. Documentos, base operativa y configuración local excluidos.',flush=True)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.CalledProcessError,urllib.error.URLError) as error:
        if isinstance(error,subprocess.CalledProcessError):message='Git no completó la operación. Revisa el mensaje anterior de autenticación o permisos.'
        elif isinstance(error,urllib.error.HTTPError):message=f'GitHub respondió HTTP {error.code}. Revisa acceso, permisos de repositorio o conectividad.'
        elif isinstance(error,urllib.error.URLError):message='No se pudo conectar con GitHub. Ejecuta SUBIR_GITHUB.bat directamente en Windows con conexión a Internet.'
        else:message=str(error)
        print('\nPublicación no completada: '+message,flush=True)
        sys.exit(1)
