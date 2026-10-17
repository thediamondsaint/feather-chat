import base64
import io
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import backend as b


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = b.Store(self.temp.name)
    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()
    def add(self, chat, text, role='user', status='complete'):
        return self.store.write('INSERT INTO messages(chat_id,role,content,status) VALUES(?,?,?,?)',(chat,role,text,status))
    def test_pagination_search_updates_and_delete(self):
        chat = self.store.chat()
        for n in range(85): self.add(chat, f'message {n}')
        rows, more = self.store.messages(chat)
        self.assertTrue(more)
        self.assertEqual(rows[0]['content'],'message 45')
        earlier, more = self.store.messages(chat,rows[0]['id'])
        self.assertEqual(earlier[-1]['content'],'message 44')
        self.assertEqual(len(self.store.listing('message 83')),1)
        self.store.write("UPDATE messages SET content='pineapple' WHERE id=?",(rows[-1]['id'],))
        self.assertEqual(len(self.store.listing('pineapp')),1)
        self.store.write('DELETE FROM chats WHERE id=?',(chat,))
        self.assertEqual(self.store.listing('pineapple'),[])
        self.assertEqual(self.store.rows('SELECT * FROM messages'),[])
    def test_project_filter_and_literal_search(self):
        self.store.write("INSERT INTO projects VALUES('p','Work','Be concise')")
        c = self.store.chat('p'); self.add(c,'select document')
        self.store.chat()
        self.assertEqual(len(self.store.listing(project='p')),1)
        self.assertEqual(len(self.store.listing('" OR select*')),0)
        self.assertEqual(len(self.store.listing('select')),1)
    def test_context_is_bounded_and_excludes_partial_replies(self):
        c=self.store.chat()
        self.add(c,'old'*100)
        self.add(c,'bad','assistant','interrupted')
        self.add(c,'recent')
        self.assertEqual(self.store.context(c,budget=20),[{'role':'user','content':'recent'}])
    def test_restart_preserves_partial_content_as_interrupted(self):
        c=self.store.chat(); self.add(c,'partial','assistant','streaming')
        second=b.Store(self.temp.name)
        self.assertEqual(second.rows('SELECT status,content FROM messages')[0],{'status':'interrupted','content':'partial'})
        second.db.close()


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.events=[]
        self.service=b.Service(self.temp.name,lambda event,**kw:self.events.append({'event':event,**kw}))
        self.service.accounts['active']='test'
        self.service.accounts['accounts']['test']={'client_id':'test','access_token':'fake-not-a-credential','expires_at':time.time()+1000,'scopes':['chatgpt.tokens.use.direct']}
        self.service.models=[{'slug':'test-model','name':'Test'}]
        self.chat=self.service.store.chat()
        self.service.store.write("INSERT INTO messages(chat_id,role,content) VALUES(?,'user','Hello')",(self.chat,))
        self.mid=self.service.store.write("INSERT INTO messages(chat_id,role,content,status) VALUES(?,'assistant','','streaming')",(self.chat,))
        self.job={'chat':self.chat,'mid':self.mid,'cancel':threading.Event(),'socket':None}
        self.service.active_job=self.job
    def tearDown(self):
        self.service.store.db.close(); self.temp.cleanup()
    def run_stream(self,events):
        wire=''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode()
        seen=[]
        def response(req,timeout):
            seen.append(json.loads(req.data)); return io.BytesIO(wire)
        with patch.object(b.urllib.request,'urlopen',side_effect=response):
            self.service.stream(self.job,'test-model')
        self.assertFalse(seen[0]['store']); self.assertTrue(seen[0]['stream'])
        self.assertNotIn('max_output_tokens',seen[0])
        return self.service.store.rows('SELECT * FROM messages WHERE id=?',(self.mid,))[0]
    def test_success_requires_terminal_event(self):
        row=self.run_stream([{'type':'response.output_text.delta','delta':'Hi '},{'type':'response.output_text.delta','delta':'there'},{'type':'response.completed'}])
        self.assertEqual((row['content'],row['status']),('Hi there','complete'))
        self.assertIsNone(self.service.active_job)
        self.assertEqual(''.join(e['text'] for e in self.events if e['event']=='delta'),'Hi there')
    def test_disconnect_saves_partial_and_reports_error(self):
        row=self.run_stream([{'type':'response.output_text.delta','delta':'Partial'}])
        self.assertEqual((row['content'],row['status']),('Partial','interrupted'))
        self.assertTrue(any(e['event']=='error' for e in self.events))
    def test_failure_after_delta_never_marks_complete(self):
        row=self.run_stream([{'type':'response.output_text.delta','delta':'Beginning'},{'type':'response.failed','response':{'error':{'code':'subscription_sharing_usage_limit_exceeded'}}}])
        self.assertEqual(row['status'],'interrupted')
        self.assertIn('usage_limit',self.events[-1]['message'])
    def test_cancel_does_not_make_request(self):
        self.job['cancel'].set()
        with patch.object(b.urllib.request,'urlopen') as network: self.service.stream(self.job,'test-model')
        network.assert_not_called()
        self.assertEqual(self.service.store.rows('SELECT status FROM messages WHERE id=?',(self.mid,))[0]['status'],'stopped')
    def test_refresh_retains_rotated_tokens(self):
        account=self.service.account()
        account.update(expires_at=0,refresh_token='old')
        with patch.object(b,'request_json',return_value={'access_token':'renewed','refresh_token':'rotated','expires_in':3600}) as req:
            self.assertEqual(self.service.token(),'renewed')
        self.assertEqual(account['refresh_token'],'rotated')
        self.assertEqual(req.call_args.args[1]['client_id'],'test')
        self.assertNotIn('scope',req.call_args.args[1])
        self.assertEqual(self.service.creds_path.stat().st_mode & 0o777,0o600)
    def test_scopes_are_required(self):
        self.service.account()['scopes']=[]
        with self.assertRaises(RuntimeError): self.service.token()
    def test_fts_export_and_project_dispatch(self):
        self.service.active_job=None
        self.service.dispatch({'op':'project','id':'test-p','name':'Laptop','instructions':'Short answers'})
        self.service.dispatch({'op':'move','chat':self.chat,'project':'test-p'})
        self.service.dispatch({'op':'rename','chat':self.chat,'title':'Laptop tips'})
        self.service.dispatch({'op':'export','chat':self.chat})
        files=list((Path(self.temp.name)/'exports').glob('*.md'))
        self.assertEqual(len(files),1)
        self.assertIn('Hello',files[0].read_text())
        self.assertEqual(self.service.store.listing(project='test-p')[0]['title'],'Laptop tips')
    def test_sse_comments_and_multiline(self):
        wire=io.BytesIO(b': heartbeat\r\ndata: {"type":\r\ndata: "response.completed"}\r\n\r\ndata: [DONE]\n\n')
        self.assertEqual(list(b.sse_events(wire)),[{'type':'response.completed'}])


class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.key=Path(cls.temp.name)/'private.pem'
        subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048','-out',str(cls.key)],check=True,capture_output=True)
        result=subprocess.run(['openssl','rsa','-in',str(cls.key),'-noout','-modulus'],check=True,capture_output=True,text=True)
        modulus=int(result.stdout.strip().split('=')[1],16)
        cls.jwks={'keys':[{'kty':'RSA','kid':'test','n':b.b64(modulus.to_bytes(256,'big')),'e':b.b64((65537).to_bytes(3,'big'))}]}
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def token(self,**changes):
        claims={'iss':b.AUTH,'sub':'person','aud':'client','nonce':'nonce','iat':int(time.time()),'exp':int(time.time()+60),**changes}
        data=b.b64(json.dumps({'alg':'RS256','kid':'test'}).encode())+'.'+b.b64(json.dumps(claims).encode())
        sig=subprocess.run(['openssl','dgst','-sha256','-sign',str(self.key)],input=data.encode(),check=True,capture_output=True).stdout
        return data+'.'+b.b64(sig)
    def verify(self,token):
        return b.validate_id_token(token,'client','nonce',{'issuer':b.AUTH},self.jwks)
    def test_valid_signed_identity(self): self.assertEqual(self.verify(self.token())['sub'],'person')
    def test_rejects_wrong_nonce_audience_issuer_and_expiry(self):
        for change in ({'nonce':'evil'},{'aud':'wrong'},{'iss':'https://evil.test'},{'exp':0},{'iat':time.time()+500}):
            with self.subTest(change=change), self.assertRaises(RuntimeError): self.verify(self.token(**change))
    def test_rejects_tampered_identity(self):
        token=self.token(); head,payload,sig=token.split('.')
        claims=json.loads(b.unb64(payload)); claims['sub']='attacker'
        with self.assertRaises(RuntimeError): self.verify(head+'.'+b.b64(json.dumps(claims).encode())+'.'+sig)


class OAuthFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.events=[]
        self.service=b.Service(self.temp.name,lambda event,**kw:self.events.append({'event':event,**kw}))
        self.urls=[]
        self.callbacks=[]
    def tearDown(self):
        self.service.store.db.close(); self.temp.cleanup()
    def flow(self, wrong_state=False, returning=False):
        service=self.service
        urls=self.urls
        if returning:
            service.accounts['active']='issued'
            service.accounts['accounts']['issued']={'client_id':'issued','subject':'person','email':'person@example.test','id_token':'previous','access_token':'old','scopes':['chatgpt.tokens.use.direct']}
        class Server:
            server_port=43210
            def __init__(server,address,handler):
                self.assertEqual(address,('127.0.0.1',0)); server.handler=handler
            def __enter__(server): return server
            def __exit__(server,*args): pass
            def handle_request(server):
                params=b.urllib.parse.parse_qs(b.urllib.parse.urlsplit(urls[0]).query)
                handler=object.__new__(server.handler)
                handler.path='/auth/callback?'+b.urllib.parse.urlencode({'state':'WRONG' if wrong_state else params['state'][0],'client_id':'issued','code':'test-code'})
                handler.wfile=io.BytesIO(); handler.send_response=lambda *_:None
                handler.send_header=lambda *_:None; handler.end_headers=lambda:None
                handler.do_GET()
                if wrong_state: service.login_cancel.set()
        def browser(args,**kwargs): urls.append(args[1])
        def api(url,data=None,**kwargs):
            self.callbacks.append((url,data))
            if url.endswith('/oauth/token'):
                return {'access_token':'new-access','refresh_token':'new-refresh','id_token':'signed-id','expires_in':3600,'scope':b.SCOPES}
            if url.endswith('openid-configuration'): return {'issuer':b.AUTH,'jwks_uri':b.AUTH+'/.well-known/jwks.json'}
            if url.endswith('jwks.json'): return {'keys':[]}
            if url.endswith('/models'): return {'models':[{'slug':'model-a','display_name':'Model A','visibility':'list'}]}
            raise AssertionError('Unexpected request')
        def validate(token,client,nonce,config,jwks):
            params=b.urllib.parse.parse_qs(b.urllib.parse.urlsplit(urls[0]).query)
            self.assertEqual(nonce,params['nonce'][0]); self.assertEqual(client,'issued')
            return {'sub':'person','email':'person@example.test'}
        with patch.object(b.http.server,'HTTPServer',Server), patch.object(b.subprocess,'Popen',side_effect=browser), patch.object(b,'request_json',side_effect=api), patch.object(b,'validate_id_token',side_effect=validate):
            service.login()
        return b.urllib.parse.parse_qs(b.urllib.parse.urlsplit(urls[0]).query)
    def test_initial_dynamic_registration_pkce_and_scope(self):
        params=self.flow()
        self.assertEqual(params['client_id'],['dynamic_agent_client'])
        self.assertEqual(params['agent_name_hint'],[b.APP])
        self.assertEqual(params['code_challenge_method'],['S256'])
        exchange=self.callbacks[0][1]
        self.assertEqual(exchange['client_id'],'issued')
        self.assertEqual(exchange['redirect_uri'],params['redirect_uri'][0])
        self.assertEqual(b.b64(b.hashlib.sha256(exchange['code_verifier'].encode()).digest()),params['code_challenge'][0])
        self.assertEqual(self.service.accounts['active'],'issued')
        self.assertEqual(self.service.models[0]['slug'],'model-a')
    def test_returning_registration_reuses_host_client_and_hint(self):
        host=self.service.accounts['host']
        params=self.flow(returning=True)
        self.assertEqual(params['client_id'],['issued'])
        self.assertNotIn('agent_name_hint',params)
        self.assertEqual(params['ext_agent_host_id'],[host])
        self.assertEqual(params['id_token_hint'],['previous'])
    def test_bad_state_never_exchanges_code(self):
        self.flow(wrong_state=True)
        self.assertEqual(self.callbacks,[])
        self.assertEqual(self.service.accounts['active'],'')


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.events=[]
        self.service=b.Service(self.temp.name,lambda event,**kw:self.events.append({'event':event,**kw}))
    def tearDown(self):
        self.service.store.db.close(); self.temp.cleanup()
    def test_persist_restart_partial_update_and_reset(self):
        self.service.dispatch({'op':'preferences','values':{'theme':'paper','background':'grid','strength':30,'effects':False}})
        self.service.dispatch({'op':'preferences','values':{'fit':'fit'}})
        second=b.Service(self.temp.name,lambda *args,**kw:None)
        self.assertEqual(second.preferences,{'theme':'paper','background':'grid','image':'','fit':'fit','strength':30,'effects':False})
        second.store.db.close()
        self.service.dispatch({'op':'preferences','reset':True})
        self.assertEqual(self.service.preferences,b.DEFAULT_PREFERENCES)
        self.assertNotIn('access_token',self.service.preferences_path.read_text())
    def test_reject_invalid_values_without_changing_preferences(self):
        for values in ({'effects':'yes'},{'theme':'unknown'},{'strength':36},{'strength':True},{'background':'video'},{'image':'https://example.com/a.png'},{'image':'file://remote/a.png'},{'fit':'unknown'},{'access_token':'oops'},{'background':'custom'}):
            with self.subTest(values=values),self.assertRaises(RuntimeError):
                self.service.dispatch({'op':'preferences','values':values})
        self.assertEqual(self.service.preferences,b.DEFAULT_PREFERENCES)
    def test_local_image_space_and_unicode_path_stays_local(self):
        image=Path(self.temp.name)/'my café.svg'; image.write_text('<svg/>')
        self.service.dispatch({'op':'preferences','values':{'background':'custom','image':image.as_uri()}})
        self.assertEqual(self.service.preferences['image'],image.as_uri())
        image.unlink()
        self.service.dispatch({'op':'preferences','values':{'theme':'paper'}})
        self.service.dispatch({'op':'preferences','values':{'background':'none'}})
        self.service.dispatch({'op':'preferences','values':{'background':'grid'}})
        self.assertEqual(self.service.preferences['background'],'grid')
        # Missing images do not break startup; the UI can show a fallback and select a replacement.
        second=b.Service(self.temp.name,lambda *args,**kw:None)
        self.assertEqual(second.preferences['background'],'grid')
        second.store.db.close()
    def test_bad_preferences_file_falls_back_without_touching_history(self):
        self.service.preferences_path.write_text('{broken')
        second=b.Service(self.temp.name,lambda *args,**kw:None)
        self.assertEqual(second.preferences,b.DEFAULT_PREFERENCES)
        second.store.db.close()


class OrganizationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.events=[]
        self.service=b.Service(self.temp.name,lambda event,**kw:self.events.append({'event':event,**kw}))
        self.store=self.service.store
        self.store.write("INSERT INTO projects VALUES('p','Work','Use short answers')")
        self.chat=self.store.chat('p')
        self.store.write("INSERT INTO messages(chat_id,role,content) VALUES(?,'user','Find my pineapple notes')",(self.chat,))
    def tearDown(self):
        self.store.db.close(); self.temp.cleanup()
    def test_archive_search_scope_counts_restore_and_restart(self):
        self.service.dispatch({'op':'archive','chat':self.chat})
        self.assertEqual(self.store.listing('pineapple'),[])
        self.assertEqual(self.store.listing('pineapple',project='p',archived=True)[0]['id'],self.chat)
        self.assertEqual(self.store.counts('p'),{'active':0,'archived':1})
        self.assertEqual(self.store.counts('__unfiled__'),{'active':0,'archived':0})
        second=b.Store(self.temp.name)
        self.assertEqual(second.listing(archived=True)[0]['id'],self.chat)
        second.db.close()
        self.service.dispatch({'op':'archive','chat':self.chat,'archived':False})
        self.assertEqual(len(self.store.listing('pineapple')),1)
        self.assertEqual(self.store.counts(),{'active':1,'archived':0})
    def test_folder_removal_preserves_active_and_archived_messages(self):
        other=self.store.chat('p')
        self.store.write("INSERT INTO messages(chat_id,role,content) VALUES(?,'user','Other notes')",(other,))
        self.service.dispatch({'op':'archive','chat':other})
        self.service.last_project='p'
        self.service.dispatch({'op':'delete_project','id':'p'})
        self.assertEqual(self.service.last_project,'')
        self.assertEqual(self.store.rows('SELECT project_id FROM chats'),[{'project_id':None},{'project_id':None}])
        self.assertEqual(self.store.counts('__unfiled__'),{'active':1,'archived':1})
        self.assertEqual(len(self.store.rows('SELECT * FROM messages')),2)
        self.assertEqual(len(self.store.listing('pineapple',project='__unfiled__')),1)
    def test_move_rename_and_delete_target_an_unopened_row(self):
        other=self.store.chat()
        self.service.dispatch({'op':'move','chat':self.chat,'project':''})
        self.service.dispatch({'op':'rename','chat':self.chat,'title':'Notes'})
        self.assertFalse(any(e['event']=='messages' for e in self.events))
        self.service.dispatch({'op':'archive','chat':self.chat})
        self.service.dispatch({'op':'delete','chat':self.chat})
        self.assertEqual(self.store.rows('SELECT * FROM messages WHERE chat_id=?',(self.chat,)),[])
        self.assertEqual(self.store.listing('pineapple',archived=True),[])
        self.assertEqual(self.store.listing()[0]['id'],other)
    def test_archive_and_folder_changes_cannot_disrupt_stream(self):
        self.service.active_job={'chat':self.chat}
        for req in ({'op':'archive','chat':self.chat},{'op':'delete','chat':self.chat},{'op':'delete_project','id':'p'}):
            with self.subTest(req=req),self.assertRaises(RuntimeError): self.service.dispatch(req)
        self.assertEqual(self.store.counts(),{'active':1,'archived':0})
    def test_archived_chat_rejects_send_without_appending_or_network(self):
        self.service.models=[{'slug':'test-model','name':'Test'}]
        self.service.accounts['active']='test'
        self.service.accounts['accounts']['test']={'access_token':'not-a-real-token'}
        self.service.dispatch({'op':'archive','chat':self.chat})
        with patch.object(self.service,'spawn') as spawn, self.assertRaisesRegex(RuntimeError,'Restore'):
            self.service.send(self.chat,'new message','test-model')
        spawn.assert_not_called()
        self.assertEqual(len(self.store.rows('SELECT * FROM messages')),1)
    def test_unfiled_new_chat_and_invalid_move(self):
        self.service.models=[{'slug':'test-model','name':'Test'}]
        self.service.accounts['active']='test'
        self.service.accounts['accounts']['test']={'access_token':'not-a-real-token'}
        self.service.last_project='__unfiled__'
        with patch.object(self.service,'spawn'):
            self.service.send('','new message','test-model')
        self.assertEqual(len(self.store.listing(project='__unfiled__')),1)
        self.assertIsNone(self.store.listing(project='__unfiled__')[0]['project_id'])
        with self.assertRaisesRegex(RuntimeError,'existing folder'):
            self.service.dispatch({'op':'move','chat':self.chat,'project':'missing'})
    def test_legacy_preferences_get_default_effects(self):
        self.service.preferences_path.write_text(json.dumps({'theme':'midnight','background':'none','image':'','fit':'crop','strength':18}))
        second=b.Service(self.temp.name,lambda *args,**kw:None)
        self.assertTrue(second.preferences['effects'])
        self.assertEqual(second.preferences['theme'],'midnight')
        second.store.db.close()


class MigrationTests(unittest.TestCase):
    def test_old_database_migrates_without_losing_history_or_folders(self):
        with tempfile.TemporaryDirectory() as folder:
            db=sqlite3.connect(Path(folder)/'history.sqlite3')
            db.executescript("""
                CREATE TABLE projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,instructions TEXT NOT NULL DEFAULT '');
                CREATE TABLE chats(id TEXT PRIMARY KEY,title TEXT NOT NULL,project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,updated REAL NOT NULL);
                CREATE TABLE messages(id INTEGER PRIMARY KEY,chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,role TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'complete');
                INSERT INTO projects VALUES('p','Legacy folder','Keep these instructions');
                INSERT INTO chats VALUES('c','Legacy conversation','p',1);
                INSERT INTO messages VALUES(1,'c','user','Keep this message','complete');
            """)
            db.close()
            store=b.Store(folder)
            self.assertEqual(store.listing()[0]['archived'],0)
            self.assertEqual(store.listing()[0]['project_id'],'p')
            self.assertEqual(store.context('c')[0]['content'],'Keep this message')
            store.db.close()
            second=b.Store(folder)
            self.assertEqual(second.counts(),{'active':1,'archived':0})
            self.assertEqual(second.rows('SELECT instructions FROM projects')[0]['instructions'],'Keep these instructions')
            second.db.close()


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.events = []
        self.service = b.Service(self.temp.name, lambda event, **kw: self.events.append(dict(event=event, **kw)))
        self.service.accounts['active'] = 'a'
        for key in ('a', 'b'):
            self.service.accounts['accounts'][key] = dict(client_id=key, email='same@example.test',
                access_token='fake-'+key, refresh_token='refresh-'+key, expires_at=time.time()+1000,
                scopes=['chatgpt.tokens.use.direct'], models=[dict(slug=key, name=key)], model=key)
        self.service.cached_models()
        self.events.clear()

    def tearDown(self):
        self.service.store.db.close()
        self.temp.cleanup()

    def test_switch_restores_catalog_and_model_before_network(self):
        with patch.object(self.service, 'spawn') as spawn:
            self.service.dispatch(dict(op='switch', id='b'))
            self.assertEqual(self.service.model, 'b')
            self.assertEqual([e['event'] for e in self.events], ['account', 'models'])
            self.assertEqual(self.events[0]['active'], 'b')
            self.assertNotEqual(self.events[0]['accounts'][0]['label'], self.events[0]['accounts'][1]['label'])
            self.assertNotIn('fake-', json.dumps(self.events))
            spawn.assert_called_once_with(self.service.discover, 'b', 1)
        restored = b.Service(self.temp.name, lambda *args, **kw: None)
        restored.cached_models()
        self.assertEqual(restored.model, 'b')
        restored.store.db.close()

    def test_profile_preference_and_scope_isolation(self):
        with patch.object(self.service, 'spawn'):
            self.service.account()['models'].append(dict(slug='a2', name='a2'))
            self.service.cached_models()
            self.service.dispatch(dict(op='model', model='a2'))
            self.service.dispatch(dict(op='switch', id='b'))
            self.assertEqual(self.service.model, 'b')
            self.service.dispatch(dict(op='switch', id='a'))
            self.assertEqual(self.service.model, 'a2')
            self.service.accounts['accounts']['b']['scopes'] = []
            self.service.dispatch(dict(op='switch', id='b'))
            self.assertEqual(self.service.models, [])
            self.assertEqual(self.service.model, '')

    def test_switch_guards_and_same_profile_noop(self):
        with patch.object(self.service, 'spawn') as spawn:
            self.service.dispatch(dict(op='switch', id='a'))
            spawn.assert_not_called()
            self.assertEqual(self.service.auth_generation, 0)
            for field in ('active_job', 'account_busy'):
                setattr(self.service, field, True)
                with self.assertRaises(RuntimeError): self.service.dispatch(dict(op='switch', id='b'))
                setattr(self.service, field, None if field == 'active_job' else False)
            with self.assertRaises(RuntimeError): self.service.dispatch(dict(op='switch', id='missing'))

    def test_slow_old_catalog_and_error_never_replace_new_profile(self):
        for fails in (False, True):
            with self.subTest(fails=fails):
                self.service.accounts['active'] = 'a'
                self.service.auth_generation += 1
                entered, release = threading.Event(), threading.Event()
                def request(*args, **kw):
                    self.assertEqual(kw['token'], 'fake-a')
                    entered.set()
                    if not release.wait(3): raise RuntimeError('test timed out')
                    if fails: raise RuntimeError('old profile failure')
                    return dict(models=[dict(slug='stale', visibility='list')])
                with patch.object(b, 'request_json', side_effect=request), patch.object(self.service, 'spawn'):
                    worker = threading.Thread(target=self.service.discover)
                    worker.start()
                    try:
                        self.assertTrue(entered.wait(2))
                        self.service.dispatch(dict(op='switch', id='b'))
                        self.events.clear()
                    finally:
                        release.set()
                        worker.join(3)
                    self.assertFalse(worker.is_alive())
                    self.assertEqual(self.service.model, 'b')
                    self.assertEqual(self.events, [])

    def test_switch_does_not_wait_for_token_refresh(self):
        entered, release = threading.Event(), threading.Event()
        self.service.account()['expires_at'] = 0
        def request(url, *args, **kw):
            if url.endswith('/oauth/token'):
                entered.set()
                if not release.wait(3): raise RuntimeError('test timed out')
                return dict(access_token='renewed-a', refresh_token='rotated-a', expires_in=3600)
            return dict(models=[dict(slug='a', visibility='list')])
        with patch.object(b, 'request_json', side_effect=request), patch.object(self.service, 'spawn'):
            worker = threading.Thread(target=self.service.discover)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                started = time.monotonic()
                self.service.dispatch(dict(op='switch', id='b'))
                self.assertLess(time.monotonic()-started, .5)
                self.assertEqual(self.service.model, 'b')
            finally:
                release.set()
                worker.join(3)
            self.assertEqual(self.service.accounts['accounts']['a']['access_token'], 'renewed-a')
            self.assertEqual(self.service.account()['access_token'], 'fake-b')

    def test_rapid_round_trip_restarts_stale_catalog_load(self):
        with patch.object(self.service, 'spawn') as spawn:
            self.service.refresh_models()
            self.service.dispatch(dict(op='switch', id='b'))
            self.service.dispatch(dict(op='switch', id='a'))
            self.assertEqual(spawn.call_count, 2)
            # The original A worker starts after the user has already returned.
            with patch.object(b, 'request_json') as network:
                self.service.discover('a', 0)
                network.assert_not_called()
            self.assertEqual(spawn.call_count, 3)
            self.assertEqual(spawn.call_args.args, (self.service.discover, 'a', 2))

    def test_catalog_refresh_is_deduplicated_and_persisted(self):
        with patch.object(self.service, 'spawn') as spawn:
            self.service.refresh_models()
            self.service.refresh_models()
            spawn.assert_called_once()
        with patch.object(b, 'request_json', return_value=dict(models=[dict(slug='new', visibility='list'), dict(slug='hidden', visibility='hide')])):
            self.service.discover('a', 0)
        self.assertEqual(self.service.model, 'new')
        self.assertEqual(self.service.account()['models'], [dict(slug='new', name='new')])
        self.assertFalse(self.service.discovering)
        self.assertEqual(json.loads(self.service.creds_path.read_text())['accounts']['a']['models'], self.service.models)


if __name__ == "__main__": unittest.main()
