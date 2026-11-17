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
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'github-source'
OWNER='oscarillo12'
NAME='ingefix-logistica'
REMOTE=f'https://github.com/{OWNER}/{NAME}.git'
AUTH_STORE=ROOT/'data'/'github-auth'
RESULT_FILE=ROOT/'data'/'publicacion-github.txt'

def run(args,**kwargs):
    if args and args[0]=='git':
        args=['git','-c','safe.directory='+SOURCE.resolve().as_posix(),'-c','credential.credentialStore=dpapi','-c','credential.dpapiStorePath='+str(AUTH_STORE),*args[1:]]
    if 'credential-manager' in args and 'login' in args:
        process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=kwargs.get('env'))
        failures=[]
        for line in process.stdout:
            print(line,end='',flush=True)
            if line.lstrip().lower().startswith('fatal:'):failures.append(line.strip())
        code=process.wait()
        if code:raise subprocess.CalledProcessError(code,args,stderr='\n'.join(failures))
        return subprocess.CompletedProcess(args,code)
    return subprocess.run(args,check=True,**kwargs)

def main():
    env=dict(os.environ)
    for key in ('GIT_TRACE','GIT_TRACE_CURL','GIT_CURL_VERBOSE','GCM_TRACE','GIT_TRACE_PACKET'):env.pop(key,None)
    if not (SOURCE/'.git').is_dir():raise ValueError('No se encuentra el repositorio preparado en github-source.')
    result=run(['git','-C',str(SOURCE),'status','--porcelain'],capture_output=True,text=True,env=env)
    if result.stdout.strip():raise ValueError('Hay cambios sin confirmar en github-source. Deben revisarse antes de publicar.')
    files=run(['git','-C',str(SOURCE),'ls-files'],capture_output=True,text=True,env=env).stdout.splitlines()
    approved_data={'data/seed.json','data/evidence.json','data/ledger.json'}
    forbidden=[p for p in files if (p.startswith('data/') and p not in approved_data) or Path(p).suffix.lower() in ('.pdf','.xlsx','.db','.log','.env') or p.endswith('.local.json')]
    if forbidden:raise ValueError('Se detectaron archivos operativos en la selección. Se detiene la publicación para revisarlos.')
    env['GCM_INTERACTIVE']='never';env['GIT_TERMINAL_PROMPT']='0'
    request=f'protocol=https\nhost=github.com\nusername={OWNER}\n\n'
    # Consulta primero la sesión de Windows; solo inicia el flujo de dispositivo si no hay credencial guardada.
    credential=subprocess.run(['git','-C',str(SOURCE),'-c','safe.directory='+SOURCE.resolve().as_posix(),'-c','credential.credentialStore=dpapi','-c','credential.dpapiStorePath='+str(AUTH_STORE),'credential','fill'],input=request,capture_output=True,text=True,env=env)
    if credential.returncode or not any(line.startswith('password=') for line in credential.stdout.splitlines()):
        print('Se necesita autorizar GitHub. El código temporal aparecerá en esta ventana negra.',flush=True)
        print('Abre https://github.com/login/device y escribe ahí el código que aparece aquí.',flush=True)
        webbrowser.open('https://github.com/login/device')
        run(['git','credential-manager','github','login','--username',OWNER,'--device','--no-ui'],env=env)
        credential=subprocess.run(['git','-C',str(SOURCE),'-c','safe.directory='+SOURCE.resolve().as_posix(),'-c','credential.credentialStore=dpapi','-c','credential.dpapiStorePath='+str(AUTH_STORE),'credential','fill'],input=request,capture_output=True,text=True,env=env,check=True)
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
    print('PASO 2/3: Comprobar o crear el repositorio.',flush=True)
    try:repository=api(f'/repos/{OWNER}/{NAME}')
    except urllib.error.HTTPError as error:
        if error.code!=404:raise
        repository=api('/user/repos',dict(name=NAME,private=True,description='Control logístico INGEFIX: inventario, conteo cíclico y reposición',auto_init=False))
    print('Destino verificado:',repository['html_url'],'· estado:',('privado' if repository.get('private') else 'público'),flush=True)
    remote=run(['git','-C',str(SOURCE),'remote','get-url','origin'],capture_output=True,text=True,env=env).stdout.strip()
    if remote!=REMOTE:raise ValueError('El destino origin no coincide con el repositorio previsto.')
    print('PASO 3/3: Subir el codigo y verificar el commit publicado.',flush=True)
    run(['git','-C',str(SOURCE),'push','-u','origin','main'],env=env)
    local=run(['git','-C',str(SOURCE),'rev-parse','HEAD'],capture_output=True,text=True,env=env).stdout.strip()
    published=run(['git','-C',str(SOURCE),'ls-remote','origin','refs/heads/main'],capture_output=True,text=True,env=env).stdout.split()
    if not published or published[0]!=local:raise ValueError('No se pudo verificar que GitHub tenga el último commit.')
    print('\nPUBLICACIÓN VERIFICADA: '+repository['html_url'],flush=True)
    print('Documentos originales, base operativa y configuración local excluidos.',flush=True)

def execute():
    try:
        main()
        result=f'PUBLICACION VERIFICADA\nhttps://github.com/{OWNER}/{NAME}\n'
        status=0
    except (ValueError,OSError,subprocess.CalledProcessError,urllib.error.URLError) as error:
        if isinstance(error,subprocess.CalledProcessError):message='Git no completo la operacion. '+(error.stderr or '')+'\nSi indica socket, red o plataforma no permitida, ejecuta SUBIR_GITHUB.bat desde el Explorador de Windows, fuera de ChatGPT/Codex.'
        elif isinstance(error,urllib.error.HTTPError):message=f'GitHub respondio HTTP {error.code}. Revisa permisos o conectividad.'
        elif isinstance(error,urllib.error.URLError):message='No se pudo conectar con GitHub. Ejecuta el iniciador desde Windows con acceso a Internet.'
        else:message=str(error)
        result='PUBLICACION NO COMPLETADA\n'+message+'\n\nEl aviso Presione una tecla solo cierra la consola: no inicia la autorizacion.\n'
        print('\n'+result,flush=True);status=1
    RESULT_FILE.parent.mkdir(exist_ok=True)
    RESULT_FILE.write_text(datetime.now().isoformat()+'\n'+result,encoding='utf-8')
    return status

if __name__=='__main__':
    sys.exit(execute())
