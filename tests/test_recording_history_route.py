"""Compatibility contract for the legacy recording history registration."""
import unittest
from unittest.mock import patch

import httpx
import live_auto_recorder as core
import app_entry


class RecordingHistoryRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = app_entry.app
        self.app.dependency_overrides[core.requireLogin] = lambda: True
        self.addCleanup(self.app.dependency_overrides.pop, core.requireLogin, None)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")
        self.addAsyncCleanup(self.client.aclose)

    def test_registration_and_app_identity(self):
        self.assertIs(self.app, core.app)
        self.assertIs(self.app.state.lar_runtime, app_entry.runtime)
        self.assertIs(app_entry.runtime.core, core)
        routes = self.app.routes
        history = [r for r in routes if getattr(r, 'path', None) == '/api/recording_history']
        self.assertEqual(len(history), 1)
        route = history[0]
        self.assertEqual(route.methods, {'GET'})
        self.assertEqual(route.name, 'api_recording_history')
        self.assertIs(route.endpoint, core.api_recording_history)
        self.assertIs(route.dependant.dependencies[0].call, core.requireLogin)
        self.assertEqual(str(self.app.url_path_for('api_recording_history')), '/api/recording_history')
        flattened = []
        for item in routes:
            flattened.extend(getattr(getattr(item, 'original_router', None), 'routes', [item]))
        telegram = [r for r in flattened if getattr(r, 'path', None) == '/api/test_telegram' and 'GET' in getattr(r, 'methods', set())]
        self.assertEqual(len(telegram), 2)
        self.assertIs(telegram[0].endpoint, core.testTelegram)
        self.assertLess(routes.index(telegram[0]), routes.index(route))
        export = next(r for r in routes if getattr(r, 'path', None) == '/api/config_export')
        self.assertLess(routes.index(route), routes.index(export))

    async def test_history_contract_and_filters(self):
        with patch.object(core, 'get_history', return_value=[{'event': 'start'}]) as history, patch.object(core, 'get_recording_stats', return_value={'total': 1}):
            response = await self.client.get('/api/recording_history')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'status': 'success', 'history': [{'event': 'start'}], 'stats': {'total': 1}})
            history.assert_called_with(limit=50, channel_id=None, event=None)
            response = await self.client.get('/api/recording_history', params={'limit': 999, 'channel_id': 'abc', 'event': 'stop'})
            self.assertEqual(response.status_code, 200)
            history.assert_called_with(limit=200, channel_id='abc', event='stop')
            self.assertEqual((await self.client.get('/api/recording_history?limit=bad')).status_code, 422)
        with patch.object(core, 'get_history', side_effect=RuntimeError('failure')):
            response = await self.client.get('/api/recording_history')
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json(), {'status': 'error', 'message': 'failure'})
