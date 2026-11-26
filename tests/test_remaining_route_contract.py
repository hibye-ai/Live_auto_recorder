"""Synthetic contracts for legacy shell, notification and retention handlers."""
import asyncio
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import httpx
import app_entry
import live_auto_recorder as core


class RemainingRouteContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = app_entry.app
        self.old = {k: getattr(self.app.state, k, None) for k in ('channels', 'channels_lock', 'fsm', 'config')}
        self.addCleanup(lambda: [setattr(self.app.state, k, v) for k, v in self.old.items()])
        self.app.state.channels = []
        self.app.state.channels_lock = asyncio.Lock()
        self.app.state.fsm = Mock()
        self.app.state.config = {'loginMode':False, 'autoRecordingMode':False}
        self.app.dependency_overrides[core.requireLogin] = lambda: True
        self.addCleanup(self.app.dependency_overrides.pop, core.requireLogin, None)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://localhost')
        self.addAsyncCleanup(self.client.aclose)

    async def test_legacy_pages_and_assets(self):
        for path, phrase in (('/', '녹화 대시보드'), ('/recording', 'start-all-recording')):
            response = await self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(phrase, response.text)
            self.assertEqual(response.text.count('/static/css/console.css?'), 1)
            self.assertIn('/static/css/app.css?', response.text)

    async def test_telegram_first_registration_and_core_patch_point(self):
        with patch.object(core, 'loadConfig', return_value={'telegram_enabled': True}), patch.object(core, 'loadTelegram', return_value={'telegram_bot_token':'synthetic', 'telegram_chat_id':'test'}), patch.object(core.requests, 'get', return_value=Mock(status_code=200)) as upstream:
            response = await self.client.get('/api/test_telegram')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['status'], 'success')
            upstream.assert_called_once()
        with patch.object(core, 'loadConfig', return_value={'telegram_enabled': False}), patch.object(core, 'loadTelegram', return_value={}), patch.object(core.requests, 'get') as upstream:
            response = await self.client.get('/api/test_telegram')
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()['status'], 'error')
            upstream.assert_not_called()

    async def test_cleanup_dry_run_and_mocked_delete(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'LAR_V2_ENABLED':'0'}):
            old = os.path.join(root, 'old.ts')
            recent = os.path.join(root, 'new.mp4')
            other = os.path.join(root, 'ignore.txt')
            for path in (old, recent, other):
                with open(path, 'wb') as stream:
                    stream.write(b'synthetic')
            os.utime(old, (1, 1))
            response = await self.client.post('/api/file_cleanup', json={'path':root, 'mode':'age', 'age_days':1, 'dry_run':True})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual((data['status'], data['total_files'], data['to_delete_count'], data['deleted']), ('success', 2, 1, []))
            self.assertEqual(data['candidates'][0]['name'], 'old.ts')
            self.assertTrue(os.path.exists(old))
            with patch.object(core.os, 'remove') as remove:
                response = await self.client.post('/api/file_cleanup', json={'path':root, 'mode':'age', 'age_days':1, 'dry_run':False})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['deleted'], ['old.ts'])
                remove.assert_called_once_with(old)
            self.assertTrue(os.path.exists(old))
            response = await self.client.post('/api/file_cleanup', json={'path':os.path.join(root, 'missing')})
            self.assertEqual(response.status_code, 400)
        with patch.dict(os.environ, {'LAR_V2_ENABLED':'1'}):
            response = await self.client.post('/api/file_cleanup', json={})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()['code'], 'REFERENCE_AWARE_CLEANUP_REQUIRED')
