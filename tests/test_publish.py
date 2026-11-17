import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import publish_github as publish

class PublishTests(unittest.TestCase):
    def test_private_push_is_verified_and_token_not_printed(self):
        self.exercise(private=True)
    def test_public_repository_is_not_pushed(self):
        self.exercise(private=False)
    def exercise(self,private):
        calls=[];sha='1'*40
        def run(args,**kwargs):
            calls.append(args)
            if 'status' in args:output=''
            elif 'ls-files' in args:output='app/server.py\nREADME.md\n'
            elif 'fill' in args:output='username=oscarillo12\npassword=FAKE-TEST-ONLY\n'
            elif 'get-url' in args:output=publish.REMOTE
            elif 'rev-parse' in args:output=sha
            elif 'ls-remote' in args:output=sha+'\trefs/heads/main\n'
            else:output=''
            return subprocess.CompletedProcess(args,0,stdout=output)
        class Response:
            def __init__(self,body):self.body=body
            def __enter__(self):return io.StringIO(json.dumps(self.body))
            def __exit__(self,*args):pass
        responses=[Response({'login':'oscarillo12'}),Response({'private':private,'html_url':'https://github.com/oscarillo12/ingefix-logistica'})]
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory);(source/'.git').mkdir();out=io.StringIO()
            with patch.object(publish,'SOURCE',source),patch.object(publish,'run',side_effect=run),patch.object(publish.webbrowser,'open'),patch.object(publish.urllib.request,'urlopen',side_effect=responses),contextlib.redirect_stdout(out):
                if private:publish.main()
                else:
                    with self.assertRaises(ValueError):publish.main()
            self.assertNotIn('FAKE-TEST-ONLY',out.getvalue())
            self.assertEqual(any('push' in call for call in calls),private)
            if private:self.assertIn('PUBLICACIÓN VERIFICADA',out.getvalue())

if __name__=='__main__':unittest.main()
