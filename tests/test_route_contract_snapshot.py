"""Freeze assembled route order and authentication dependencies across refactors."""
import json
import unittest
from pathlib import Path

from fastapi.routing import APIRoute, APIWebSocketRoute
import app_entry
import live_auto_recorder as core


def route_contract(routes, prefix=''):
    result = []
    for route in routes:
        router = getattr(route, 'original_router', None)
        if router is not None:
            result.extend(route_contract(router.routes, prefix + route.include_context.prefix))
        elif isinstance(route, (APIRoute, APIWebSocketRoute)):
            result.append({
                'path': prefix + route.path,
                'methods': sorted(route.methods) if isinstance(route, APIRoute) else ['WEBSOCKET'],
                'name': route.name,
                'endpoint': f'{route.endpoint.__module__}.{route.endpoint.__qualname__}',
                'dependencies': [f'{dep.call.__module__}.{dep.call.__qualname__}' for dep in route.dependant.dependencies],
            })
    return result


class RouteContractSnapshotTests(unittest.TestCase):
    def test_ordered_route_contract(self):
        expected = json.loads((Path(__file__).parent / 'fixtures' / 'route_contract.json').read_text())
        self.assertEqual(route_contract(app_entry.app.routes), expected)

    def test_compatibility_identity_and_runtime(self):
        self.assertIs(app_entry.app, core.app)
        self.assertIs(app_entry.app.state.lar_runtime, app_entry.runtime)
        self.assertIs(app_entry.runtime.core, core)
        self.assertTrue(callable(core.api_config_export))
        self.assertTrue(callable(core.api_config_import))


class CoreStateContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_state_and_callables(self):
        import asyncio
        import os
        from unittest.mock import AsyncMock, Mock, patch
        from fastapi import FastAPI

        app = FastAPI()
        channels = []
        config = {'autoRecordingMode': False}
        fsm = Mock(stopAll=AsyncMock())
        saver = Mock(flush=AsyncMock())
        async def no_work(*args, **kwargs):
            pass
        with (
            patch.dict(os.environ, {'LAR_V2_ENABLED': '0'}),
            patch.object(core, 'loadChannels', return_value=channels),
            patch.object(core, 'loadConfig', return_value=config),
            patch.object(core, 'loadCookies', return_value={'cookie': 'test'}),
            patch.object(core, 'yloadCookies', return_value='test-cookie'),
            patch.object(core, 'ChannelFsm', return_value=fsm),
            patch.object(core, 'coerceChannelsInplace', return_value=False),
            patch.object(core, 'initChannelStates', new=AsyncMock()),
            patch.object(core, '_makeMetaFetcher', return_value=no_work),
            patch.object(core, 'DebouncedSaver', return_value=saver),
            patch.object(core, 'mc_ensure'),
            patch.object(core, '_seedMetadataWEB', new=no_work),
            patch.object(core, 'mc_refreshLoop', new=no_work),
            patch.object(core.RecorderManager, 'setChannels'),
            patch.object(core.RecorderManager, 'setChannelsRef'),
            patch.object(core.RecorderManager, 'setChannelsLockRef'),
            patch('module.cifs_watchdog.start_cifs_watchdog'),
            patch('module.cifs_watchdog.stop_cifs_watchdog', new=AsyncMock()),
            patch('module.live_recorder.closeHttpxClient', new=AsyncMock()),
        ):
            async with core.lifespan(app):
                self.assertIs(app.state.channels, channels)
                self.assertIs(app.state.config, config)
                self.assertIs(app.state.fsm, fsm)
                self.assertIsInstance(app.state.channels_lock, asyncio.Lock)
                self.assertEqual(app.state.chzzk_cookies, {'cookie': 'test'})
                self.assertEqual(app.state.youtube_cookie_path, 'test-cookie')
                self.assertIsInstance(app.state.bg_tasks, set)
                self.assertIs(app.state.meta_fetcher, no_work)
                self.assertIs(app.state.save_debounced, saver)
                await app.state.meta_fetcher()
                await app.state.save_debounced.flush()
            self.assertEqual(saver.flush.await_count, 2)
            fsm.stopAll.assert_awaited_once()
