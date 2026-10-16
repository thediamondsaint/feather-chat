#!/usr/bin/env python3
"""Feather: small, event-driven local chat service. No third-party Python packages."""
import base64
import hashlib
import hmac
import http.server
import json
import os
from pathlib import Path
import queue
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

APP = 'FeatherGPT'
AUTH = 'https://auth.openai.com'
API = 'https://api.openai.com/v1'
RESOURCE = API
SCOPES = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
DEFAULT_PREFERENCES = {'theme':'forest','background':'none','image':'','fit':'crop','strength':18,'effects':True}


def validate_preferences(values, current=None, check_image=True):
    if not isinstance(values, dict) or set(values) - set(DEFAULT_PREFERENCES):
        raise RuntimeError('The appearance settings were invalid.')
    result = {**DEFAULT_PREFERENCES, **(current or {}), **values}
    if type(result['effects']) is not bool:
        raise RuntimeError('Effects must be enabled or disabled.')
    if result['theme'] not in ('forest','midnight','plum','paper'):
        raise RuntimeError('Choose an available theme.')
    if result['background'] not in ('none','contours','grid','horizon','custom'):
        raise RuntimeError('Choose an available background.')
    if result['fit'] not in ('crop','fit'):
        raise RuntimeError('Choose a supported image fit.')
    if type(result['strength']) is not int or not 0 <= result['strength'] <= 35:
        raise RuntimeError('Background strength must be between 0 and 35 percent.')
    if not isinstance(result['image'],str):
        raise RuntimeError('Choose a local image file.')
    if result['image']:
        url = urllib.parse.urlsplit(result['image'])
        if url.scheme != 'file' or url.netloc not in ('','localhost') or url.query or url.fragment:
            raise RuntimeError('Choose a local image file, rather than an internet URL.')
        path = Path(urllib.parse.unquote(url.path)).resolve()
        if check_image and (result['image'] != (current or {}).get('image','') or (result['background'] == 'custom' and (current or {}).get('background') != 'custom')):
            if path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.svg') or not path.is_file():
                raise RuntimeError('Choose an existing PNG, JPEG, WebP or SVG image.')
            if path.stat().st_size > 50 * 1024 * 1024:
                raise RuntimeError('Choose an image smaller than 50 MB.')
        result['image'] = path.as_uri()
    if result['background'] == 'custom' and not result['image']:
        raise RuntimeError('Choose an image before enabling a custom background.')
    return result


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def unb64(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def atomic_json(path, value):
    path = Path(path)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.save-')
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(value, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def request_json(url, data=None, token=None, form=False):
    headers = {'User-Agent': 'FeatherChat/0.1', 'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        data = (urllib.parse.urlencode(data) if form else json.dumps(data)).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data, headers), timeout=25) as response:
            body = response.read(2_000_000)
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        try:
            value = json.loads(exc.read(65536)).get('error', {})
            detail = value.get('message', value.get('code', '')) if isinstance(value, dict) else str(value)
        except (ValueError, AttributeError):
            detail = ''
        raise RuntimeError(f'OpenAI returned HTTP {exc.code}. {detail[:400]}') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError('Could not connect to OpenAI. Check your connection and try again.') from None


def der(tag, data):
    size = len(data)
    length = bytes([size]) if size < 128 else bytes([128 + (size.bit_length() + 7) // 8]) + size.to_bytes((size.bit_length() + 7) // 8, 'big')
    return bytes([tag]) + length + data


def rsa_pem(jwk):
    def integer(value):
        raw = unb64(value).lstrip(b'\0') or b'\0'
        return der(2, (b'\0' if raw[0] & 128 else b'') + raw)
    key = der(48, integer(jwk['n']) + integer(jwk['e']))
    spki = der(48, bytes.fromhex('300d06092a864886f70d0101010500') + der(3, b'\0' + key))
    encoded = base64.b64encode(spki).decode()
    return '-----BEGIN PUBLIC KEY-----\n' + '\n'.join(encoded[i:i+64] for i in range(0, len(encoded), 64)) + '\n-----END PUBLIC KEY-----\n'


def validate_id_token(token, client_id, nonce, config, jwks):
    """Reject unverified identity. Delegate RSA cryptography to system OpenSSL."""
    try:
        head, payload, signature = token.split('.')
        header, claims = json.loads(unb64(head)), json.loads(unb64(payload))
        if header.get('alg') != 'RS256':
            raise ValueError('Unsupported identity signature algorithm')
        key = next(k for k in jwks['keys'] if k.get('kid') == header.get('kid') and k.get('kty') == 'RSA' and k.get('use', 'sig') == 'sig')
        with tempfile.TemporaryDirectory(prefix='feather-verify-') as folder:
            pub, sig = Path(folder)/'key.pem', Path(folder)/'signature'
            pub.write_text(rsa_pem(key))
            sig.write_bytes(unb64(signature))
            result = subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(pub), '-signature', str(sig)], input=(head+'.'+payload).encode(), capture_output=True, timeout=5)
        if result.returncode:
            raise ValueError('Invalid identity signature')
        audiences = claims.get('aud', [])
        audiences = [audiences] if isinstance(audiences, str) else audiences
        if claims.get('iss') != AUTH or config.get('issuer') != AUTH or client_id not in audiences:
            raise ValueError('Identity issuer or audience mismatch')
        if len(audiences) > 1 and claims.get('azp') != client_id:
            raise ValueError('Identity authorized party mismatch')
        if 'iat' not in claims or float(claims.get('exp', 0)) <= time.time() or float(claims['iat']) > time.time()+60 or float(claims.get('nbf', 0)) > time.time()+5:
            raise ValueError('Identity token expired or not yet valid')
        if not isinstance(claims.get('sub'), str) or not claims['sub'] or not hmac.compare_digest(str(claims.get('nonce', '')), nonce):
            raise ValueError('Identity nonce mismatch')
        return claims
    except (KeyError, StopIteration, TypeError, ValueError) as exc:
        raise RuntimeError('Sign-in identity could not be verified. Please try again.') from exc


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.folder, 0o700)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.folder/'history.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          PRAGMA journal_mode=WAL;
          PRAGMA foreign_keys=ON;
          PRAGMA cache_size=-2048;
          CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,instructions TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY,title TEXT NOT NULL,project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,updated REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,role TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'complete');
          CREATE INDEX IF NOT EXISTS messages_chat ON messages(chat_id,id);
          CREATE INDEX IF NOT EXISTS chats_updated ON chats(updated DESC);
          CREATE INDEX IF NOT EXISTS chats_project ON chats(project_id,updated DESC);
          CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(content,chat_id UNINDEXED,tokenize='unicode61');
          CREATE TRIGGER IF NOT EXISTS message_insert AFTER INSERT ON messages BEGIN
            INSERT INTO search(rowid,content,chat_id) VALUES(new.id,new.content,new.chat_id); END;
          CREATE TRIGGER IF NOT EXISTS message_delete AFTER DELETE ON messages BEGIN DELETE FROM search WHERE rowid=old.id; END;
          CREATE TRIGGER IF NOT EXISTS message_update AFTER UPDATE OF content ON messages BEGIN
            DELETE FROM search WHERE rowid=old.id;
            INSERT INTO search(rowid,content,chat_id) VALUES(new.id,new.content,new.chat_id); END;
        ''')
        # Additive migration: existing conversations and folder membership stay intact.
        if 'archived' not in {row['name'] for row in self.db.execute('PRAGMA table_info(chats)')}:
            self.db.execute('ALTER TABLE chats ADD COLUMN archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1))')
        self.db.execute('CREATE INDEX IF NOT EXISTS chats_archive_updated ON chats(archived,updated DESC)')
        self.db.execute('CREATE INDEX IF NOT EXISTS chats_folder_archive ON chats(project_id,archived,updated DESC)')
        # A killed app must not turn a partial reply into completed context on restart.
        self.db.execute("UPDATE messages SET status='interrupted' WHERE status='streaming'")
        self.db.commit()

    def rows(self, sql, params=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, params)]

    def write(self, sql, params=()):
        with self.lock, self.db:
            cur = self.db.execute(sql, params)
            return cur.lastrowid

    def chat(self, project=None):
        key = uuid.uuid4().hex
        self.write('INSERT INTO chats(id,title,project_id,updated) VALUES(?,?,?,?)', (key,'New conversation',project or None,time.time()))
        return key

    def listing(self, query='', project='', limit=60, archived=False):
        where, params = ['archived=?'], [int(archived)]
        if project == '__unfiled__':
            where.append('project_id IS NULL')
        elif project:
            where.append('project_id=?')
            params.append(project)
        if query.strip():
            words = re.findall(r'\w+', query, re.UNICODE)[:12]
            if words:
                match = ' AND '.join('"'+w+'"*' for w in words)
                where.append('(id IN (SELECT chat_id FROM search WHERE search MATCH ?) OR title LIKE ?)')
                params.extend([match, '%'+query+'%'])
            else:
                where.append('title LIKE ?')
                params.append('%'+query+'%')
        sql = 'SELECT * FROM chats' + (' WHERE '+' AND '.join(where) if where else '')
        return self.rows(sql+' ORDER BY updated DESC LIMIT ?', (*params, min(int(limit),10000)))

    def counts(self, project=''):
        where, params = '', ()
        if project == '__unfiled__':
            where = ' WHERE project_id IS NULL'
        elif project:
            where, params = ' WHERE project_id=?', (project,)
        return self.rows('SELECT COALESCE(SUM(archived=0),0) AS active, COALESCE(SUM(archived=1),0) AS archived FROM chats'+where,params)[0]

    def messages(self, chat, before=0, limit=40):
        rows = self.rows('SELECT * FROM messages WHERE chat_id=? AND id<? ORDER BY id DESC LIMIT ?', (chat, before or 2**63-1,limit+1))
        return list(reversed(rows[:limit])), len(rows)>limit

    def context(self, chat, budget=48000):
        rows = self.rows("SELECT role,content FROM messages WHERE chat_id=? AND status='complete' ORDER BY id DESC LIMIT 32", (chat,))
        result, size = [], 0
        for row in rows:
            if size + len(row['content']) > budget:
                break
            result.append(row)
            size += len(row['content'])
        return list(reversed(result))


class Service:
    def __init__(self, folder, emit=None):
        self.store = Store(folder)
        self.folder = Path(folder)
        self.emit = emit or self.output
        self.output_lock = threading.Lock()
        self.auth_lock = threading.RLock()
        self.preferences_path = self.folder/'preferences.json'
        try:
            self.preferences = validate_preferences(json.loads(self.preferences_path.read_text()), check_image=False)
        except (OSError, ValueError, RuntimeError, TypeError):
            self.preferences = dict(DEFAULT_PREFERENCES)
        self.creds_path = self.folder/'accounts.json'
        try:
            self.accounts = json.loads(self.creds_path.read_text())
        except (OSError, ValueError):
            self.accounts = {'active':'','accounts':{},'host':'urn:uuid:'+str(uuid.uuid4())}
            self.save_accounts()
        self.active_job = None
        self.login_cancel = threading.Event()
        self.login_running = False
        self.account_busy = False
        self.auth_generation = 0
        self.models = []
        self.model = ''
        self.last_query = ''
        self.last_project = ''
        self.last_archived = False
        self.list_limit = 60

    def output(self, event, **fields):
        with self.output_lock:
            print(json.dumps({'event':event, **fields}, ensure_ascii=False), flush=True)

    def save_accounts(self):
        atomic_json(self.creds_path, self.accounts)

    def account(self):
        return self.accounts['accounts'].get(self.accounts.get('active'), {})

    def state(self):
        account = self.account()
        self.emit('account', connected=bool(account.get('access_token')), label=account.get('email',''), plan_enabled='chatgpt.tokens.use.direct' in account.get('scopes',[]), accounts=[{'id':k, 'label':v.get('email','Account')+' · '+k[-6:], 'connected':bool(v.get('access_token'))} for k,v in self.accounts['accounts'].items()], active=self.accounts.get('active',''))

    def listing(self):
        rows = self.store.listing(self.last_query, self.last_project, self.list_limit+1, self.last_archived)
        self.emit('chats', rows=rows[:self.list_limit], more=len(rows)>self.list_limit, counts=self.store.counts(self.last_project))
        self.emit('projects', rows=self.store.rows('SELECT * FROM projects ORDER BY name COLLATE NOCASE'))

    def load(self, chat, before=0):
        rows, more = self.store.messages(chat, before)
        info = self.store.rows('SELECT * FROM chats WHERE id=?', (chat,))
        if not info:
            raise RuntimeError('Conversation no longer exists.')
        self.emit('messages', chat=chat, info=info[0], rows=rows, more=more, prepend=bool(before))

    def spawn(self, fn, *args):
        def work():
            try:
                fn(*args)
            except Exception as exc:
                self.emit('error', message=str(exc)[:500] if isinstance(exc, RuntimeError) else 'The operation failed. Please try again.')
        threading.Thread(target=work, daemon=True).start()

    def token(self):
        with self.auth_lock:
            account = self.account()
            if not account.get('access_token'):
                raise RuntimeError('Choose Continue with ChatGPT to connect your account first.')
            if 'chatgpt.tokens.use.direct' not in account.get('scopes', []):
                raise RuntimeError('ChatGPT plan access was not granted. Sign in again and enable it.')
            if account.get('expires_at',0) < time.time()+90:
                if not account.get('refresh_token'):
                    raise RuntimeError('Your session has expired. Please sign in again.')
                tokens = request_json(AUTH+'/api/accounts/oauth/token', {'grant_type':'refresh_token','client_id':account['client_id'],'refresh_token':account['refresh_token'],'resource':RESOURCE}, form=True)
                account.update({k:v for k,v in tokens.items() if k in ('access_token','refresh_token','id_token')})
                account['expires_at'] = time.time()+tokens.get('expires_in',3600)
                if 'scope' in tokens:
                    account['scopes'] = tokens['scope'].split()
                self.save_accounts()
                if 'chatgpt.tokens.use.direct' not in account['scopes']:
                    raise RuntimeError('ChatGPT plan access is no longer enabled. Please sign in again.')
            return account['access_token']

    def discover(self):
        generation = self.auth_generation
        data = request_json(API+'/models', token=self.token())
        rows = [{'slug':m['slug'],'name':m.get('display_name',m['slug'])} for m in data.get('models',[]) if m.get('visibility')=='list']
        if not rows:
            raise RuntimeError('No eligible models were returned for this ChatGPT account.')
        if generation != self.auth_generation:
            return
        self.models = rows
        preferred = self.account().get('model','')
        self.model = preferred if preferred in [r['slug'] for r in rows] else rows[0]['slug']
        self.emit('models', rows=rows, selected=self.model)

    def login(self, new=False):
        self.login_cancel.clear()
        generation = self.auth_generation
        state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        old = {} if new else dict(self.account())
        result = queue.Queue(maxsize=1)
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(handler):
                parsed = urllib.parse.urlsplit(handler.path)
                params = urllib.parse.parse_qs(parsed.query)
                valid = parsed.path == '/auth/callback' and hmac.compare_digest(params.get('state',[''])[0], state)
                handler.send_response(200 if valid else 400)
                handler.send_header('Content-Type','text/html; charset=utf-8')
                handler.send_header('Cache-Control','no-store')
                handler.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'")
                handler.end_headers()
                handler.wfile.write(('<html><body style="background:#171a19;color:#e8eee9;font:20px sans-serif;padding:64px"><h1>FeatherGPT</h1>'+('Return to FeatherGPT to finish connecting. You can close this tab.' if valid else 'Invalid sign-in callback. Return to Feather and try again.')+'</body></html>').encode())
                if valid and result.empty():
                    result.put_nowait(params)
        try:
            with http.server.HTTPServer(('127.0.0.1',0), Handler) as server:
                server.timeout = .5
                callback = f'http://127.0.0.1:{server.server_port}/auth/callback'
                params = {'client_id':old.get('client_id','dynamic_agent_client'),'ext_agent_host_id':self.accounts['host'],'response_type':'code','redirect_uri':callback,'scope':SCOPES,'resource':RESOURCE,'state':state,'nonce':nonce,'code_challenge_method':'S256','code_challenge':b64(hashlib.sha256(verifier.encode()).digest())}
                if not old:
                    params['agent_name_hint'] = APP
                else:
                    if old.get('id_token'):
                        params['id_token_hint'] = old['id_token']
                    if old.get('email'):
                        params['login_hint'] = old['email']
                # The URL may contain an ID-token hint: never emit or log it.
                subprocess.Popen(['xdg-open',AUTH+'/api/accounts/authorize?'+urllib.parse.urlencode(params)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.monotonic()+180
                while result.empty() and time.monotonic()<deadline and not self.login_cancel.is_set():
                    server.handle_request()
                if self.login_cancel.is_set():
                    return
                if result.empty():
                    raise RuntimeError('Sign-in timed out. Choose Continue with ChatGPT to try again.')
                values = result.get()
            if values.get('error'):
                raise RuntimeError('Sign-in was declined or unavailable. You can try again when ready.')
            client = values.get('client_id',[old.get('client_id','')])[0]
            if not client or client == 'dynamic_agent_client' or (old and old['client_id'] != client):
                raise RuntimeError('The sign-in registration was incomplete. Please try again.')
            if not values.get('code'):
                raise RuntimeError('Sign-in did not return an authorization code.')
            tokens = request_json(AUTH+'/api/accounts/oauth/token', {'grant_type':'authorization_code','client_id':client,'code':values['code'][0],'code_verifier':verifier,'redirect_uri':callback,'resource':RESOURCE}, form=True)
            config = request_json(AUTH+'/.well-known/openid-configuration')
            jwks_url = config.get('jwks_uri','')
            if urllib.parse.urlsplit(jwks_url).scheme != 'https' or urllib.parse.urlsplit(jwks_url).hostname != 'auth.openai.com':
                raise RuntimeError('The OpenAI identity configuration was unexpected.')
            claims = validate_id_token(tokens.get('id_token',''),client,nonce,config,request_json(jwks_url))
            if old and claims['sub'] != old['subject']:
                raise RuntimeError('The returned account does not match the selected registration.')
            with self.auth_lock:
                if generation != self.auth_generation or self.login_cancel.is_set():
                    return
                account = {**old, 'client_id':client,'subject':claims['sub'],'email':claims.get('email',claims.get('name','ChatGPT account')),'scopes':tokens.get('scope','').split(),'expires_at':time.time()+tokens.get('expires_in',3600)}
                account.update({k:tokens[k] for k in ('access_token','refresh_token','id_token') if k in tokens})
                self.accounts['accounts'][client] = account
                self.accounts['active'] = client
                self.auth_generation += 1
                self.save_accounts()
            self.state()
            if 'chatgpt.tokens.use.direct' in account['scopes']:
                self.discover()
        finally:
            self.login_running = False
            self.account_busy = False
            self.emit('auth_busy', busy=False)

    def end_session(self):
        try:
            self.signout()
        finally:
            self.account_busy = False
            self.emit('auth_busy', busy=False)

    def signout(self):
        with self.auth_lock:
            account = self.account()
            confirmed = False
            try:
                if account.get('refresh_token'):
                    config = request_json(AUTH+'/.well-known/openid-configuration')
                    endpoint = config.get('revocation_endpoint','')
                    if urllib.parse.urlsplit(endpoint).scheme != 'https' or urllib.parse.urlsplit(endpoint).hostname != 'auth.openai.com':
                        raise RuntimeError('Unexpected revocation endpoint')
                    request_json(endpoint, {'token':account['refresh_token'],'token_type_hint':'refresh_token','client_id':account['client_id']}, form=True)
                confirmed = True
            except RuntimeError:
                pass
            for key in ('access_token','refresh_token','id_token'):
                account.pop(key,None)
            self.auth_generation += 1
            self.models, self.model = [], ''
            self.save_accounts()
        self.state()
        self.emit('models',rows=[],selected='')
        self.emit('notice',message='Signed out.' if confirmed else 'Signed out locally. Remote revocation was not confirmed; disconnect Feather in ChatGPT Settings if needed.')

    def send(self, chat, text, model):
        if self.account_busy:
            raise RuntimeError('Finish connecting your account before sending a message.')
        if self.active_job:
            raise RuntimeError('Wait for the current reply, or stop it first.')
        if not text.strip() or len(text)>24000:
            raise RuntimeError('Enter a message of up to 24,000 characters.')
        if model not in [m['slug'] for m in self.models]:
            raise RuntimeError('Connect your account and select an available model first.')
        if not self.account().get('access_token'):
            raise RuntimeError('Sign in before sending a message.')
        if not chat:
            chat = self.store.chat(None if self.last_project == '__unfiled__' else self.last_project)
        info = self.store.rows('SELECT archived FROM chats WHERE id=?', (chat,))
        if not info:
            raise RuntimeError('Conversation no longer exists.')
        if info[0]['archived']:
            raise RuntimeError('Restore this conversation from the archive before sending a message.')
        self.store.write('INSERT INTO messages(chat_id,role,content) VALUES(?,?,?)',(chat,'user',text.strip()))
        self.store.write("UPDATE chats SET title=CASE WHEN title='New conversation' THEN ? ELSE title END,updated=? WHERE id=?", (' '.join(text.split())[:70],time.time(),chat))
        mid = self.store.write("INSERT INTO messages(chat_id,role,content,status) VALUES(?,'assistant','','streaming')",(chat,))
        self.load(chat)
        self.listing()
        job = {'chat':chat,'mid':mid,'cancel':threading.Event(),'socket':None}
        self.active_job = job
        self.emit('busy',busy=True,chat=chat)
        self.spawn(self.stream, job, model)

    def cancel(self):
        job = self.active_job
        if job:
            job['cancel'].set()
            sock = job.get('socket')
            if sock:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def stream(self, job, model):
        text, pending, status, last, checkpoint = '', '', 'interrupted', time.monotonic(), time.monotonic()
        error = None
        try:
            token = self.token()
            if job['cancel'].is_set():
                return
            context = self.store.context(job['chat'])
            project = self.store.rows('SELECT p.instructions FROM projects p JOIN chats c ON c.project_id=p.id WHERE c.id=?',(job['chat'],))
            payload = {'model':model,'input':context,'store':False,'stream':True}
            if project and project[0]['instructions']:
                payload['instructions'] = project[0]['instructions']
            request = urllib.request.Request(API+'/responses',json.dumps(payload).encode(),{'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'text/event-stream','User-Agent':'FeatherChat/0.1'})
            try:
                response = urllib.request.urlopen(request,timeout=30)
            except urllib.error.HTTPError as exc:
                try:
                    body = json.loads(exc.read(65536)).get('error',{})
                    detail = body.get('message',body.get('code','')) if isinstance(body,dict) else str(body)
                except ValueError:
                    detail = ''
                raise RuntimeError(f'OpenAI returned HTTP {exc.code}. {detail[:400]}') from None
            with response:
                try:
                    job['socket'] = response.fp.raw._sock
                except AttributeError:
                    pass
                if job['cancel'].is_set():
                    return
                for event in sse_events(response):
                    if job['cancel'].is_set():
                        break
                    kind = event.get('type','')
                    if kind in ('response.output_text.delta','response.refusal.delta'):
                        delta = event.get('delta','')
                        text += delta
                        pending += delta
                    elif kind == 'response.completed':
                        status = 'complete'
                        break
                    elif kind in ('error','response.failed','response.incomplete'):
                        detail = event.get('response',{}).get('error') or event.get('error') or event.get('response',{}).get('incomplete_details') or {}
                        if not isinstance(detail,dict):
                            detail = {}
                        raise RuntimeError(detail.get('message') or detail.get('code') or detail.get('reason') or 'The reply could not be completed. Try again.')
                    now = time.monotonic()
                    if pending and now-last >= .065:
                        self.emit('delta', chat=job['chat'],id=job['mid'],text=pending)
                        pending, last = '', now
                    if now-checkpoint >= 2:
                        self.store.write('UPDATE messages SET content=? WHERE id=?',(text,job['mid']))
                        checkpoint = now
            if status != 'complete' and not job['cancel'].is_set():
                raise RuntimeError('The connection ended before the reply completed. The partial reply is saved.')
        except Exception as exc:
            if not job['cancel'].is_set():
                error = str(exc)[:500] if isinstance(exc,RuntimeError) else 'Connection interrupted. Check your connection and try again.'
        finally:
            if job['cancel'].is_set():
                status = 'stopped'
            if pending:
                self.emit('delta',chat=job['chat'],id=job['mid'],text=pending)
            self.store.write('UPDATE messages SET content=?,status=? WHERE id=?',(text,status,job['mid']))
            job['socket'] = None
            self.active_job = None
            self.emit('finished',chat=job['chat'],id=job['mid'],status=status)
            self.emit('busy',busy=False,chat=job['chat'])
            if error:
                self.emit('error',message=error)

    def dispatch(self, req):
        op = req.get('op')
        if op == 'init':
            self.emit('preferences',values=self.preferences)
            self.state()
            self.listing()
            self.emit('ready')
            if self.account().get('access_token'):
                self.spawn(self.discover)
        elif op == 'preferences':
            updated = dict(DEFAULT_PREFERENCES) if req.get('reset') else validate_preferences(req.get('values',{}),self.preferences)
            atomic_json(self.preferences_path,updated)
            self.preferences = updated
            self.emit('preferences',values=updated)
        elif op == 'list':
            self.last_query = str(req.get('query',''))[:200]
            self.last_project = req.get('project','')
            if type(req.get('archived',False)) is not bool:
                raise RuntimeError('Choose Active or Archived conversations.')
            self.last_archived = req.get('archived',False)
            self.list_limit = min(max(60,int(req.get('limit',60))),10000)
            self.listing()
        elif op == 'load':
            self.load(req['chat'],int(req.get('before',0)))
        elif op == 'send':
            self.send(req.get('chat',''),req.get('text',''),req.get('model',''))
        elif op == 'stop':
            self.cancel()
        elif op == 'login':
            if not self.account_busy and not self.active_job:
                self.login_running = True
                self.account_busy = True
                self.emit('auth_busy',busy=True)
                self.spawn(self.login,req.get('new',False))
        elif op == 'cancel_login':
            self.login_cancel.set()
        elif op == 'models':
            if not self.account_busy:
                self.spawn(self.discover)
        elif op == 'model':
            value = req['model']
            if value in [m['slug'] for m in self.models]:
                self.model = value
                self.account()['model'] = value
                with self.auth_lock:
                    self.save_accounts()
        elif op in ('switch','signout'):
            if self.active_job or self.account_busy:
                raise RuntimeError('Finish or cancel the current operation before changing accounts.')
            if op == 'signout':
                self.account_busy = True
                self.emit('auth_busy',busy=True)
                self.spawn(self.end_session)
            else:
                if req['id'] not in self.accounts['accounts']:
                    raise RuntimeError('Unknown account.')
                self.accounts['active'] = req['id']
                self.auth_generation += 1
                self.models, self.model = [], ''
                self.save_accounts()
                self.state()
                self.emit('models',rows=[],selected='')
                if self.account().get('access_token'):
                    self.spawn(self.discover)
        elif op == 'project':
            name = str(req.get('name','')).strip()[:80]
            if not name:
                raise RuntimeError('Give the folder a name.')
            key = req.get('id') or uuid.uuid4().hex
            self.store.write('INSERT INTO projects VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,instructions=excluded.instructions',(key,name,str(req.get('instructions',''))[:12000]))
            self.listing()
            self.emit('notice',message='Folder saved.')
        elif op == 'delete_project':
            if self.active_job:
                raise RuntimeError('Finish or stop the current reply before removing a folder.')
            project = req['id']
            if not self.store.rows('SELECT id FROM projects WHERE id=?',(project,)):
                raise RuntimeError('Folder no longer exists.')
            self.store.write('DELETE FROM projects WHERE id=?',(project,))
            if self.last_project == project:
                self.last_project = ''
            self.emit('folder_deleted',id=project)
            self.listing()
            self.emit('notice',message='Folder removed. Its conversations are now Unfiled.')
        elif op in ('rename','move','delete','archive'):
            chat = req['chat']
            if self.active_job and self.active_job['chat']==chat:
                raise RuntimeError('Stop the reply before changing this conversation.')
            info = self.store.rows('SELECT title,archived FROM chats WHERE id=?',(chat,))
            if not info:
                raise RuntimeError('Conversation no longer exists.')
            if op == 'archive':
                archived = req.get('archived',True)
                if type(archived) is not bool:
                    raise RuntimeError('Choose Archive or Restore for this conversation.')
                self.store.write('UPDATE chats SET archived=? WHERE id=?',(int(archived),chat))
                self.emit('archived',chat=chat,archived=archived,title=info[0]['title'])
            elif op == 'rename':
                title = str(req.get('title','')).strip()[:100]
                if not title:
                    raise RuntimeError('Enter a conversation title.')
                self.store.write('UPDATE chats SET title=? WHERE id=?',(title,chat))
                self.emit('renamed',chat=chat,title=title)
            elif op == 'move':
                project = req.get('project') or None
                if project and not self.store.rows('SELECT id FROM projects WHERE id=?',(project,)):
                    raise RuntimeError('Choose an existing folder, or Unfiled.')
                self.store.write('UPDATE chats SET project_id=? WHERE id=?',(project,chat))
                self.emit('moved',chat=chat,project=project or '')
            else:
                self.store.write('DELETE FROM chats WHERE id=?',(chat,))
                self.emit('deleted',chat=chat)
            self.listing()
        elif op == 'export':
            chat = req['chat']
            info = self.store.rows('SELECT * FROM chats WHERE id=?',(chat,))
            if not info:
                raise RuntimeError('Conversation no longer exists.')
            folder = self.folder/'exports'
            folder.mkdir(exist_ok=True, mode=0o700)
            path = folder/(re.sub(r'[^\w -]','',info[0]['title'])[:60]+'-'+chat[:8]+'.md')
            rows = self.store.rows('SELECT * FROM messages WHERE chat_id=? ORDER BY id',(chat,))
            path.write_text('# '+info[0]['title']+'\n\n'+'\n\n'.join('## '+r['role'].capitalize()+'\n\n'+r['content'] for r in rows))
            self.emit('notice',message='Saved to '+str(path))
        else:
            raise RuntimeError('Unknown command.')


def sse_events(stream):
    """Parse SSE across arbitrary byte boundaries, comments and multi-line payloads."""
    data = []
    for raw in stream:
        line = raw.decode('utf-8').rstrip('\r\n')
        if not line:
            if data:
                payload = '\n'.join(data)
                data = []
                if payload == '[DONE]':
                    return
                yield json.loads(payload)
        elif line.startswith('data:'):
            data.append(line[5:].lstrip(' '))
    if data and '\n'.join(data) != '[DONE]':
        yield json.loads('\n'.join(data))


def main():
    os.umask(0o077)
    folder = os.environ.get('FEATHER_DATA_DIR') or str(Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'feather-chat')
    service = Service(folder)
    for line in sys.stdin:
        try:
            service.dispatch(json.loads(line))
        except Exception as exc:
            message = str(exc)[:500] if isinstance(exc,(RuntimeError,ValueError)) else 'The operation failed. Please try again.'
            service.emit('error',message=message)
    service.login_cancel.set()
    service.cancel()


if __name__ == '__main__':
    main()
