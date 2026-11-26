"""Cached metadata routes retain their core patch points and JSON contracts."""
import asyncio
from datetime import datetime
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import FastAPI
import live_auto_recorder as core
from lar_app.routers.metadata import install_metadata_route


class MetadataRouteContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        install_metadata_route(self.app, core.update_metadata, path='/api/update_metadata/{channel_id}')
        install_metadata_route(self.app, core.api_thumbnail_status, path='/api/thumbnail_status')
        self.app.dependency_overrides[core.requireLogin] = lambda: True
        self.app.state.channels = [{'id': 'one', 'platform': 'CHZZK'}]
        self.app.state.channels_lock = asyncio.Lock()
        self.app.state.meta_fetcher = Mock()
        self.app.state.save_debounced = Mock()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://testserver')
        self.addAsyncCleanup(self.client.aclose)

    async def test_update_metadata_filters_and_missing_channel(self):
        self.assertEqual((await self.client.get('/api/update_metadata/missing')).status_code, 404)
        payload = {'title': '합성 방송', 'scheduled_start_time_dt': datetime(2026, 1, 2, 3, 4, 5)}
        with patch.object(core, 'getMetadataCached', new=AsyncMock(return_value=(payload, True, False))) as fetch:
            response = await self.client.get('/api/update_metadata/one')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'status':'success', 'from_cache':True, 'fresh':False, 'metadata':{'title':'합성 방송', 'scheduled_start_time_str':'2026-01-02T03:04:05'}})
            fetch.assert_awaited_once_with(self.app, 'one', 'chzzk', self.app.state.meta_fetcher, self.app.state.save_debounced, self.app.state.channels_lock)

    async def test_thumbnail_schema_and_state_callable_arguments(self):
        items = [{'id': 'one', 'platform': 'chzzk', 'thumbnail_url': '/test.png'}]
        with patch.object(core, 'getThumbnailsCached', new=AsyncMock(return_value=items)) as fetch:
            response = await self.client.get('/api/thumbnail_status')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'channels': items})
            fetch.assert_awaited_once_with(self.app, self.app.state.channels, self.app.state.meta_fetcher, self.app.state.save_debounced, self.app.state.channels_lock)
