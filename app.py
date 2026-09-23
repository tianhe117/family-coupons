"""One process, one JSON file, one template. Run production with one Gunicorn worker."""
import json
import os
import re
import secrets
import struct
import tempfile
import threading
import time
import uuid
import zlib
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, make_response, render_template, request
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash


class Problem(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def text(value, maximum=500):
    return isinstance(value, str) and 0 < len(value.strip()) <= maximum


def valid_date(value):
    try:
        return isinstance(value, str) and value.endswith('Z') and datetime.fromisoformat(value.replace('Z', '+00:00')) is not None
    except ValueError:
        return False


def validate(data):
    try:
        assert data['schemaVersion'] == 1 and valid_date(data['updatedAt'])
        assert all(text(data['settings'][k], 1000) and data['settings'][k].startswith('scrypt:') for k in ('accessPasswordHash', 'adminPasswordHash'))
        assert isinstance(data['coupons'], list) and isinstance(data['events'], list)
        ids, numbers, events = set(), set(), set()
        for c in data['coupons']:
            assert text(c['id']) and text(c['number']) and text(c['password'])
            assert c['id'] not in ids and c['number'] not in numbers
            assert valid_date(c['createdAt']) and c['status'] in ('unused', 'used')
            assert c['usedAt'] is None if c['status'] == 'unused' else valid_date(c['usedAt'])
            ids.add(c['id'])
            numbers.add(c['number'])
        for e in data['events']:
            assert text(e['id']) and e['id'] not in events and text(e['type']) and valid_date(e['at'])
            assert 'couponId' not in e or e['couponId'] in ids
            events.add(e['id'])
    except (AssertionError, KeyError, TypeError, AttributeError):
        raise Problem('数据文件异常，已停止操作，请联系家人处理。', 503) from None
    return data


def read_data(path):
    try:
        return validate(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError):
        raise Problem('无法读取数据文件，请联系家人处理。', 503) from None


def write_data(path, data):
    validate(data)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
            temp = f.name
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    except OSError:
        raise Problem('保存失败，原数据未更改，请稍后重试。', 503) from None
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(DATA_FILE=os.getenv('DATA_FILE', 'data/data.json'),
                      INITIAL_ACCESS_PASSWORD=os.getenv('INITIAL_ACCESS_PASSWORD', ''),
                      INITIAL_ADMIN_PASSWORD=os.getenv('INITIAL_ADMIN_PASSWORD', ''),
                      COOKIE_SECURE=os.getenv('COOKIE_SECURE', 'true').lower() == 'true',
                      MAX_CONTENT_LENGTH=256 * 1024)
    if config:
        app.config.update(config)
    path = Path(app.config['DATA_FILE'])
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        access, admin = app.config['INITIAL_ACCESS_PASSWORD'], app.config['INITIAL_ADMIN_PASSWORD']
        if not isinstance(access, str) or not re.fullmatch(r'[0-9]{1,32}', access) or not text(admin, 128) or len(admin) < 8:
            raise RuntimeError('首次启动请设置数字 INITIAL_ACCESS_PASSWORD 和至少8位 INITIAL_ADMIN_PASSWORD。')
        write_data(path, {'schemaVersion': 1, 'settings': {'accessPasswordHash': generate_password_hash(access), 'adminPasswordHash': generate_password_hash(admin)}, 'coupons': [], 'events': [], 'updatedAt': now()})
    read_data(path)
    # Probe writability without touching the existing data file.
    with tempfile.TemporaryFile(dir=path.parent):
        pass
    lock = threading.RLock()
    sessions, grants, attempts = {}, {}, {}

    def body():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise Problem('请求格式错误。')
        return value

    def authenticate(d, password, role):
        stamp = time.monotonic()
        key = (request.remote_addr, role)
        for old in list(attempts):
            attempts[old] = [t for t in attempts[old] if stamp - t < 300]
            if not attempts[old]:
                del attempts[old]
        history = attempts.get(key, [])
        if len(history) >= 10:
            raise Problem('尝试次数较多，请5分钟后再试。', 429)
        if not isinstance(password, str) or len(password) > 128 or not check_password_hash(d['settings'][role + 'PasswordHash'], password):
            attempts[key] = history + [stamp]
            raise Problem('密码不正确，请重试', 401)
        attempts.pop(key, None)

    def admin_session():
        token = request.cookies.get('admin_session', '')
        session = sessions.get(token)
        if not session or session['expires'] < time.monotonic():
            sessions.pop(token, None)
            raise Problem('请重新输入管理员密码。', 401)
        if request.method != 'GET' and not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), session['csrf']):
            raise Problem('操作验证失效，请重新登录。', 403)
        session['expires'] = time.monotonic() + 1800
        return session

    def event_id(b):
        try:
            return str(uuid.UUID(b.get('operationId', '')))
        except (ValueError, TypeError, AttributeError):
            raise Problem('操作编号无效。') from None

    def remaining(d):
        return sum(c['status'] == 'unused' for c in d['coupons'])

    def record(d, ident, kind, coupon_id=None):
        e = {'id': ident, 'type': kind, 'at': now()}
        if coupon_id:
            e['couponId'] = coupon_id
        d['events'].append(e)
        d['updatedAt'] = e['at']
        write_data(path, d)

    @app.errorhandler(Problem)
    def problem(e):
        return jsonify(error=e.message), e.status

    @app.errorhandler(HTTPException)
    def http_error(e):
        return jsonify(error='请求无法处理，请检查后重试。'), e.code

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.before_request
    def same_origin():
        if request.method == 'POST' and (not request.is_json or request.headers.get('Sec-Fetch-Site') == 'cross-site'):
            raise Problem('请求来源无效。', 403)

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/health')
    def health():
        with lock:
            read_data(path)
        return jsonify(ok=True)

    @app.get('/api/status')
    def status():
        with lock:
            return jsonify(empty=remaining(read_data(path)) == 0)

    @app.post('/api/unlock')
    def unlock():
        b = body()
        with lock:
            d = read_data(path)
            authenticate(d, b.get('password'), 'access')
            # Reconciliation never returns a new coupon.
            if b.get('operationId'):
                ident = event_id(b)
                return jsonify(saved=any(e['id'] == ident and e['type'] == 'used' for e in d['events']), remaining=remaining(d))
            current = next((c for c in d['coupons'] if c['status'] == 'unused'), None)
            if current is None:
                return jsonify(empty=True)
            stamp = time.monotonic()
            for token in list(grants):
                if grants[token]['expires'] < stamp:
                    del grants[token]
            token = secrets.token_urlsafe(32)
            grants[token] = {'couponId': current['id'], 'number': current['number'], 'password': current['password'], 'expires': stamp + 600, 'operationId': None}
            return jsonify(coupon=current, remaining=remaining(d), token=token)

    @app.post('/api/use')
    def use():
        b = body()
        ident = event_id(b)
        with lock:
            d = read_data(path)
            grant = grants.get(request.headers.get('Authorization', '').removeprefix('Bearer '))
            if not grant or grant['expires'] < time.monotonic():
                raise Problem('请重新输入密码。', 401)
            if grant['operationId'] not in (None, ident):
                raise Problem('本次授权已经使用，请重新输入密码。', 409)
            existing = next((e for e in d['events'] if e['id'] == ident), None)
            if existing:
                if existing['type'] != 'used' or existing.get('couponId') != grant['couponId']:
                    raise Problem('操作编号冲突。', 409)
                return jsonify(saved=True, remaining=remaining(d))
            c = next((c for c in d['coupons'] if c['id'] == grant['couponId']), None)
            if not c or c['status'] != 'unused' or c['number'] != grant['number'] or c['password'] != grant['password']:
                raise Problem('这张券已使用或已修改，请重新输入密码。', 409)
            c['status'], c['usedAt'] = 'used', now()
            record(d, ident, 'used', c['id'])
            grant['operationId'] = ident
            return jsonify(saved=True, remaining=remaining(d))

    @app.post('/api/admin/login')
    def admin_login():
        b = body()
        with lock:
            authenticate(read_data(path), b.get('password'), 'admin')
            for key in list(sessions):
                if sessions[key]['expires'] < time.monotonic():
                    del sessions[key]
            sessions.pop(request.cookies.get('admin_session', ''), None)
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            sessions[token] = {'csrf': csrf, 'expires': time.monotonic() + 1800}
            response = jsonify(csrf=csrf)
            response.set_cookie('admin_session', token, httponly=True, secure=app.config['COOKIE_SECURE'], samesite='Strict', max_age=1800)
            return response

    @app.post('/api/admin/logout')
    def admin_logout():
        with lock:
            admin_session()
            sessions.pop(request.cookies.get('admin_session'), None)
        response = jsonify(ok=True)
        response.delete_cookie('admin_session')
        return response

    @app.get('/api/admin/data')
    def admin_data():
        with lock:
            admin_session()
            d = read_data(path)
            return jsonify(coupons=d['coupons'], events=d['events'])

    @app.post('/api/admin/change')
    def admin_change():
        b = body()
        ident, kind = event_id(b), b.get('type')
        with lock:
            admin_session()
            d = read_data(path)
            if any(e['id'] == ident for e in d['events']):
                return jsonify(saved=True)
            coupon_id = None
            if kind == 'added':
                rows = b.get('rows')
                if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
                    raise Problem('每次请添加1至1000张券。')
                seen = {c['number'] for c in d['coupons']}
                for row in rows:
                    if not isinstance(row, dict) or not text(row.get('number')) or not text(row.get('password')):
                        raise Problem('卡号和密码不能为空或超过500个字符。')
                    number, password = row['number'].strip(), row['password'].strip()
                    if number in seen:
                        raise Problem('存在重复卡号，请修正后整体提交。')
                    seen.add(number)
                    d['coupons'].append({'id': str(uuid.uuid4()), 'number': number, 'password': password, 'status': 'unused', 'createdAt': now(), 'usedAt': None})
            elif kind in ('edited', 'restored'):
                coupon_id = b.get('couponId')
                c = next((c for c in d['coupons'] if c['id'] == coupon_id), None)
                if c is None:
                    raise Problem('找不到这张券。', 409)
                if kind == 'restored':
                    if c['status'] != 'used':
                        raise Problem('这张券已经是未使用状态。', 409)
                    c['status'], c['usedAt'] = 'unused', None
                else:
                    if c['status'] != 'unused':
                        raise Problem('已使用的券不能修改。', 409)
                    if not text(b.get('number')) or not text(b.get('password')):
                        raise Problem('卡号和密码不能为空或超过500个字符。')
                    number = b['number'].strip()
                    if any(x['id'] != c['id'] and x['number'] == number for x in d['coupons']):
                        raise Problem('卡号重复。')
                    c['number'], c['password'] = number, b['password'].strip()
            elif kind == 'password_changed':
                role, password = b.get('role'), b.get('password')
                if role not in ('access', 'admin') or not text(password, 128):
                    raise Problem('密码格式错误。')
                if role == 'access' and not re.fullmatch(r'[0-9]{1,32}', password):
                    raise Problem('老人密码需要1至32位数字。')
                if role == 'admin' and len(password) < 8:
                    raise Problem('管理员密码至少8位。')
                d['settings'][role + 'PasswordHash'] = generate_password_hash(password)
            else:
                raise Problem('不支持的操作。')
            record(d, ident, kind, coupon_id)
            if kind == 'password_changed':
                (grants if b['role'] == 'access' else sessions).clear()
            return jsonify(saved=True)

    @app.get('/manifest.webmanifest')
    def manifest():
        return jsonify(name='家人券夹', short_name='家人券夹', start_url='/', scope='/', display='standalone', background_color='#F7F8F5', theme_color='#F7F8F5', icons=[{'src': '/icon.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any maskable'}])

    @app.get('/icon.png')
    def icon():
        def chunk(kind, data):
            return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
        pixels = bytearray()
        for y in range(512):
            pixels.append(0)
            for x in range(512):
                card = 100 < x < 412 and 150 < y < 362
                cut = (x-100)**2+(y-256)**2 < 24**2 or (x-412)**2+(y-256)**2 < 24**2
                line = 305 < x < 312 and 180 < y < 332 and y//14 % 2 == 0
                mark = 145 < x < 260 and (211 < y < 225 or 279 < y < 293)
                pixels.extend((247, 248, 245) if card and not (cut or line or mark) else (36, 92, 72))
        png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 512, 512, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')
        response = make_response(png)
        response.mimetype = 'image/png'
        return response

    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=int(os.getenv('PORT', '8080')), debug=False)
