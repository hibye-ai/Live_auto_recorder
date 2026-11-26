"""Legacy local-account route responses, with account I/O mocked."""
import unittest
from unittest.mock import patch

import httpx
import app_entry
import live_auto_recorder as core
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from lar_app.routers.account import install_account_route


class AccountRouteContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.add_middleware(SessionMiddleware, secret_key='test-only')
        for endpoint, path, method in [(core.login, '/login', 'POST'), (core.logout, '/logout', 'GET'), (core.register_page, '/register', 'GET'), (core.register, '/register', 'POST'), (core.updateAccount, '/updateAccount', 'POST'), (core.user_info, '/user_info', 'GET')]:
            install_account_route(self.app, endpoint, path=path, method=method)
        self.app.state.config = {'enableTray': True, 'fileManagerEnabled': True, 'fileManagerRoots': ['/synthetic']}
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://testserver')
        self.addAsyncCleanup(self.client.aclose)

    async def test_login_and_redirect_contract(self):
        response = await self.client.post('/login', data={'username': 'local', 'password': 'test'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'disabled', 'message': '로그인 기능을 사용하지 않습니다.', 'redirect_url': '/'})
        self.assertEqual((await self.client.post('/login', data={})).status_code, 422)
        for method, path, body, status in [('GET', '/logout', None, 302), ('GET', '/register', None, 302), ('POST', '/register', {'username': 'a', 'password': 'b', 'password_confirm': 'b'}, 303)]:
            response = await self.client.request(method, path, data=body)
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.headers['location'], '/')

    async def test_user_info_and_mocked_account_update(self):
        with patch.object(core, 'loadAccount', return_value={'username': 'old', 'password': 'hash'}), patch.object(core, 'check_password_hash', return_value=True) as check, patch.object(core, 'generate_password_hash', return_value='new-hash'), patch.object(core, 'saveAccount') as save:
            response = await self.client.get('/user_info')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'logged_in': True, 'username': '로컬 사용자', 'config': {'loginMode': False, 'enableTray': True, 'fileManagerEnabled': True, 'fileManagerRoots': ['/synthetic']}})
            response = await self.client.post('/updateAccount', data={'username': 'new', 'current_password': 'old', 'new_password': 'new', 'new_password_confirm': 'new', 'action': 'update'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['status'], 'success')
            self.assertEqual(response.json()['redirect_url'], '/logout')
            check.assert_called_once_with('hash', 'old')
            save.assert_called_once_with({'username': 'new', 'password': 'new-hash'})

    async def test_assembled_middleware_preserves_auth_redirects(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_entry.app), base_url='http://testserver') as client:
            for method, path, status in [('POST', '/login', 303), ('GET', '/logout', 302), ('GET', '/register', 302), ('POST', '/register', 303), ('POST', '/updateAccount', 303)]:
                response = await client.request(method, path)
                self.assertEqual((response.status_code, response.headers['location']), (status, '/'))
