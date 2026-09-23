import concurrent.futures
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from app import create_app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'data.json'
        self.app = create_app({'TESTING': True, 'DATA_FILE': str(self.path), 'COOKIE_SECURE': False})
        self.client = self.app.test_client()
        result = self.client.post('/api/admin/login', json={'password': 'admin'})
        self.headers = {'X-CSRF-Token': result.json['csrf']}

    def tearDown(self):
        self.temp.cleanup()

    def change(self, **body):
        return self.client.post('/api/admin/change', json={'operationId': str(uuid.uuid4()), **body}, headers=self.headers)

    def add(self, number='001234', password='000456'):
        return self.change(type='added', rows=[{'number': number, 'password': password}])

    def unlock(self):
        return self.client.post('/api/unlock', json={'password': '123456'}).json

    def test_auth_and_csrf(self):
        self.add('private-number-00042')
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get('/api/admin/data').status_code, 401)
        self.assertEqual(self.client.post('/api/admin/change', json={}).status_code, 400)
        self.assertEqual(self.client.post('/api/admin/change', json={'operationId': str(uuid.uuid4())}).status_code, 403)
        self.assertEqual(anonymous.post('/api/unlock', json={'password': 'wrong'}).status_code, 401)
        self.assertNotIn('private-number-00042', anonymous.get('/').text)
        self.assertNotIn('PasswordHash', self.client.get('/api/admin/data').text)
        self.assertEqual(self.client.get('/').headers['Cache-Control'], 'no-store')

    def test_use_idempotency_restore_and_original_order(self):
        self.add()
        self.add('002234', '000789')
        first = self.unlock()
        self.assertEqual(first['coupon']['password'], '000456')
        self.assertEqual(first['coupon']['id'], self.unlock()['coupon']['id'])
        headers = {'Authorization': 'Bearer ' + first['token']}
        operation = str(uuid.uuid4())
        for _ in range(2):
            result = self.client.post('/api/use', json={'operationId': operation}, headers=headers)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json['remaining'], 1)
        self.assertEqual(self.client.post('/api/use', json={'operationId': str(uuid.uuid4())}, headers=headers).status_code, 409)
        self.assertEqual(len(json.loads(self.path.read_text())['events']), 3)
        checked = self.client.post('/api/unlock', json={'password': '123456', 'operationId': operation}).json
        self.assertTrue(checked['saved'])
        self.assertNotIn('coupon', checked)
        self.assertEqual(self.unlock()['coupon']['number'], '002234')
        self.assertEqual(self.change(type='restored', couponId=first['coupon']['id']).status_code, 200)
        self.assertEqual(self.unlock()['coupon']['number'], '001234')
        self.assertEqual(self.client.post('/api/use', json={'operationId': operation}, headers=headers).status_code, 200)
        self.assertEqual(self.unlock()['remaining'], 2)

    def test_batch_atomic_duplicates(self):
        self.add()
        r = self.change(type='added', rows=[{'number': 'new', 'password': '01'}, {'number': '001234', 'password': '02'}])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(len(json.loads(self.path.read_text())['coupons']), 1)

    def test_stale_coupon_and_changed_password(self):
        self.add()
        old = self.unlock()
        self.change(type='edited', couponId=old['coupon']['id'], number='001234', password='changed')
        self.assertEqual(self.client.post('/api/use', json={'operationId': str(uuid.uuid4())}, headers={'Authorization': 'Bearer ' + old['token']}).status_code, 409)
        current = self.unlock()
        self.change(type='password_changed', role='access', password='000099')
        self.assertEqual(self.client.post('/api/use', json={'operationId': str(uuid.uuid4())}, headers={'Authorization': 'Bearer ' + current['token']}).status_code, 401)

    def test_write_failure_and_corruption_do_not_overwrite(self):
        before = self.path.read_bytes()
        with patch('app.os.replace', side_effect=OSError('disk error')):
            self.assertEqual(self.add().status_code, 503)
        self.assertEqual(self.path.read_bytes(), before)
        self.path.write_text('{broken')
        self.assertEqual(self.add().status_code, 503)
        self.assertEqual(self.path.read_text(), '{broken')

    def test_concurrent_writes(self):
        def add_one(i):
            c = self.app.test_client()
            login = c.post('/api/admin/login', json={'password': 'admin'})
            return c.post('/api/admin/change', json={'operationId': str(uuid.uuid4()), 'type': 'added', 'rows': [{'number': str(i), 'password': '00'}]}, headers={'X-CSRF-Token': login.json['csrf']}).status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(add_one, range(8))), [200]*8)
        self.assertEqual(len(json.loads(self.path.read_text())['coupons']), 8)

    def test_restart_persistence_and_empty(self):
        self.assertTrue(self.unlock()['empty'])
        self.add()
        restarted = create_app({'DATA_FILE': str(self.path), 'COOKIE_SECURE': False}).test_client()
        self.assertEqual(restarted.post('/api/unlock', json={'password': '123456'}).json['coupon']['number'], '001234')

    def test_six_digit_password_and_defaults(self):
        self.assertEqual(self.client.post('/api/unlock', json={'password': '123456'}).status_code, 200)
        for invalid in ['12345', '1234567', 'abcdef', '１２３４５６']:
            self.assertEqual(self.change(type='password_changed', role='access', password=invalid).status_code, 400)
        self.assertEqual(self.change(type='password_changed', role='access', password='000001').status_code, 200)
        restarted = create_app({'DATA_FILE': str(self.path), 'COOKIE_SECURE': False}).test_client()
        self.assertEqual(restarted.post('/api/unlock', json={'password': '000001'}).status_code, 200)
        self.assertEqual(restarted.post('/api/unlock', json={'password': '123456'}).status_code, 401)

    def test_rate_limit(self):
        for _ in range(10):
            self.client.post('/api/unlock', json={'password': 'wrong'})
        self.assertEqual(self.client.post('/api/unlock', json={'password': '123456'}).status_code, 429)


if __name__ == '__main__':
    unittest.main()
