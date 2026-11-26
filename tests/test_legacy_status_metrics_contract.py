"""Deterministic contracts for legacy status and system metrics endpoints."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from starlette.websockets import WebSocketDisconnect
import app_entry
import live_auto_recorder as core


class LegacyStatusMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = app_entry.app
        self.old = {k: getattr(self.app.state, k, None) for k in ('channels', 'channels_lock', 'fsm')}
        self.addCleanup(lambda: [setattr(self.app.state, k, v) for k, v in self.old.items()])
        self.app.state.channels = [{'id': 'one', 'name': '방송', 'platform': 'CHZZK', 'output_path': '/synthetic/file.ts', 'secret': 'hidden'}]
        self.app.state.channels_lock = asyncio.Lock()
        self.app.state.fsm = Mock(getState=Mock(return_value='WATCHING'))
        self.app.dependency_overrides[core.requireLogin] = lambda: True
        self.addCleanup(self.app.dependency_overrides.pop, core.requireLogin, None)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://testserver')
        self.addAsyncCleanup(self.client.aclose)
        self.manager = Mock()
        self.manager.get_status_recording.return_value = False
        self.manager.get_status_reserved.return_value = False
        self.manager.get_tasks_process.return_value = None
        self.manager.get_recording_filename.return_value = None
        self.manager.get_recording_duration.return_value = 'fallback'
        self.manager.get_is_user_stopped.return_value = False
        self.enterContext(patch.object(core, 'recorder_manager', self.manager))
        self.enterContext(patch.object(core.RecorderManager, 'recording_start_time', {}))

    async def test_status_watching_and_public_channel_schema(self):
        response = await self.client.get('/status')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'one': {'recording': False, 'reserved': True, 'duration': '', 'filename': 'file.ts'}})
        response = await self.client.get('/api/channels')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{'id':'one', 'channel_name':'방송', 'platform':'CHZZK', 'live_title':'', 'category':'', 'thumbnail_url':''}])
        self.manager.set_status_recording.assert_not_called()

    async def test_zombie_grace_boundary_and_cleanup_effects(self):
        self.manager.get_status_recording.return_value = True
        core.RecorderManager.recording_start_time['one'] = 100
        with patch.object(core.time, 'time', return_value=107.99):
            response = await self.client.get('/status')
        self.assertEqual(response.json()['one'], {'recording':True, 'reserved':False, 'duration':'00:00:07', 'filename':'file.ts'})
        self.manager.set_status_recording.assert_not_called()
        with patch.object(core.time, 'time', return_value=108):
            response = await self.client.get('/status')
        self.assertEqual(response.json()['one'], {'recording':False, 'reserved':False, 'duration':'', 'filename':'file.ts'})
        for name, args in [('set_status_recording', ('one', False)), ('recording_remove_start_time', ('one',)), ('recording_remove_filename', ('one',)), ('clear_tasks_process', ('one',))]:
            getattr(self.manager, name).assert_called_once_with(*args)

    async def test_channel_status_success_missing_error_and_zombie(self):
        missing = await self.client.get('/api/check_status/missing')
        self.assertEqual((missing.status_code, missing.json()), (404, {'detail':'Channel not found'}))
        response = await self.client.get('/api/check_status/one')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status':'success', 'state':'예약녹화 중', 'filename':'녹화 파일이 없습니다.', 'recording_duration':'00:00:00', 'recording_start_time':'녹화 시작 시간이 설정되지 않았습니다.', 'scheduled_start_time':'예정된 라이브 방송이 없습니다.', 'stop_requested':False})
        self.manager.get_status_recording.return_value = True
        core.RecorderManager.recording_start_time['one'] = 100
        with patch.object(core.time, 'time', return_value=108):
            response = await self.client.get('/api/check_status/one')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['state'], '대기 중')
        self.manager.set_status_recording.assert_called_once_with('one', False)
        self.manager.recording_remove_start_time.assert_called_once_with('one')
        self.manager.recording_remove_filename.assert_called_once_with('one')
        self.manager.clear_tasks_process.assert_called_once_with('one')
        self.manager.get_status_recording.side_effect = RuntimeError('synthetic error')
        response = await self.client.get('/api/check_status/one')
        self.assertEqual((response.status_code, response.json()), (500, {'status':'error', 'message':'synthetic error'}))

    async def test_metrics_schema_filtering_and_failure(self):
        memory = SimpleNamespace(total=100, used=60, available=40, percent=60)
        network = [SimpleNamespace(bytes_sent=10, bytes_recv=20), SimpleNamespace(bytes_sent=14, bytes_recv=18)]
        parts = [SimpleNamespace(mountpoint='/tmp/a', fstype='tmpfs', device='tmp'), SimpleNamespace(mountpoint='/data', fstype='ext4', device='/dev/test'), SimpleNamespace(mountpoint='/data', fstype='ext4', device='/dev/test')]
        usage = SimpleNamespace(total=100, used=40, free=60, percent=40)
        with patch.object(core.psutil, 'cpu_percent', return_value=12.5), patch.object(core.psutil, 'cpu_count', return_value=4), patch.object(core.psutil, 'virtual_memory', return_value=memory), patch.object(core.psutil, 'net_io_counters', side_effect=network), patch.object(core.psutil, 'disk_partitions', return_value=parts), patch.object(core.psutil, 'disk_usage', return_value=usage), patch.object(core, '_shortDiskLabel', return_value='disk'), patch.object(core, 'time', SimpleNamespace(time=Mock(side_effect=[100, 102]))), patch.object(core.asyncio, 'sleep', new=AsyncMock()):
            response = await self.client.get('/api/sys_metrics')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'cpu':{'name':core.cpu_name, 'percent':12.5, 'cores':4}, 'memory':{'total':100,'used':60,'free':40,'percent':60.0}, 'network':{'up_bps':2.0,'down_bps':0.0,'bytes_sent':14,'bytes_recv':18}, 'disks':[{'device':'/dev/test','mountpoint':'/data','label':'disk','fstype':'ext4','total':100,'used':40,'free':60,'percent':40.0}]})
        with patch.object(core.psutil, 'cpu_percent', side_effect=RuntimeError('synthetic metrics failure')):
            response = await self.client.get('/api/sys_metrics')
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()['status'], 'error')
        self.assertEqual(response.json()['message'], 'synthetic metrics failure')
        self.assertIn('RuntimeError: synthetic metrics failure', response.json()['traceback'])

    async def test_websocket_accept_message_disconnect_without_login_dependency(self):
        socket = SimpleNamespace(accept=AsyncMock(), send_json=AsyncMock(side_effect=[None, WebSocketDisconnect()]))
        memory = SimpleNamespace(total=100, used=60, percent=60)
        network = SimpleNamespace(bytes_sent=10, bytes_recv=20)
        with patch.object(core.psutil, 'cpu_percent', return_value=12), patch.object(core.psutil, 'virtual_memory', return_value=memory), patch.object(core.psutil, 'net_io_counters', return_value=network), patch.object(core.psutil, 'disk_partitions', return_value=[]), patch.object(core.asyncio, 'sleep', new=AsyncMock()), patch.object(core.time, 'time', return_value=123):
            await core.ws_sys_metrics(socket)
        socket.accept.assert_awaited_once()
        self.assertEqual(socket.send_json.await_count, 2)
        self.assertEqual(socket.send_json.await_args_list[0].args[0], {'cpu_percent':12.0, 'cpu_name':core.cpu_name, 'mem_percent':60.0, 'mem_used':60, 'mem_total':100, 'net_up_bps':0.0, 'net_down_bps':0.0, 'disks':[], 'ts':123})
        route = next(r for r in self.app.routes if getattr(r, 'path', None) == '/ws/sys_metrics')
        self.assertIs(route.endpoint, core.ws_sys_metrics)
        self.assertEqual(route.dependant.dependencies, [])

    async def test_websocket_assembled_unauthenticated_handshake(self):
        # The existing route has no authentication dependency; record that behavior.
        sent = []
        async def receive():
            return {'type': 'websocket.connect'}
        async def send(message):
            sent.append(message)
            if message['type'] == 'websocket.send':
                raise WebSocketDisconnect()
        scope = {'type':'websocket', 'asgi':{'version':'3.0','spec_version':'2.3'}, 'scheme':'ws', 'path':'/ws/sys_metrics', 'raw_path':b'/ws/sys_metrics', 'query_string':b'', 'headers':[(b'host', b'testserver')], 'client':('127.0.0.1', 1234), 'server':('testserver', 80), 'subprotocols':[], 'root_path':''}
        memory = SimpleNamespace(total=100, used=60, percent=60)
        network = SimpleNamespace(bytes_sent=1, bytes_recv=2)
        with patch.object(core.psutil, 'cpu_percent', return_value=12), patch.object(core.psutil, 'virtual_memory', return_value=memory), patch.object(core.psutil, 'net_io_counters', return_value=network), patch.object(core.psutil, 'disk_partitions', return_value=[]), patch.object(core.asyncio, 'sleep', new=AsyncMock()), patch.object(core, 'time', SimpleNamespace(time=Mock(return_value=123))):
            await self.app(scope, receive, send)
        self.assertEqual([message['type'] for message in sent], ['websocket.accept', 'websocket.send'])
        self.assertIn('"cpu_percent":12.0', sent[1]['text'])

    async def test_auth_dependency_remains_active_for_protected_status_routes(self):
        from fastapi import HTTPException
        def deny():
            raise HTTPException(status_code=401, detail='test denied')
        self.app.dependency_overrides[core.requireLogin] = deny
        for path in ('/api/channels', '/api/check_status/one'):
            response = await self.client.get(path)
            self.assertEqual((response.status_code, response.json()), (401, {'detail':'test denied'}))

    async def test_metrics_zero_interval_and_inaccessible_disks(self):
        memory = SimpleNamespace(total=1, used=0, available=1, percent=0)
        network = [SimpleNamespace(bytes_sent=10, bytes_recv=20), SimpleNamespace(bytes_sent=11, bytes_recv=22)]
        part = SimpleNamespace(mountpoint='/inaccessible', fstype='ext4', device='test')
        with patch.object(core.psutil, 'cpu_percent', return_value=0), patch.object(core.psutil, 'cpu_count', return_value=None), patch.object(core.psutil, 'virtual_memory', return_value=memory), patch.object(core.psutil, 'net_io_counters', side_effect=network), patch.object(core.psutil, 'disk_partitions', return_value=[part]), patch.object(core.psutil, 'disk_usage', side_effect=OSError('unavailable')), patch.object(core, 'time', SimpleNamespace(time=Mock(return_value=100))), patch.object(core.asyncio, 'sleep', new=AsyncMock()):
            response = await self.client.get('/api/sys_metrics')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['network']['up_bps'], 1000.0)
        self.assertEqual(response.json()['network']['down_bps'], 2000.0)
        self.assertEqual(response.json()['disks'], [])
        self.assertIsNone(response.json()['cpu']['cores'])

    async def test_websocket_recovers_from_sampling_error_then_disconnects(self):
        socket = SimpleNamespace(accept=AsyncMock(), send_json=AsyncMock(side_effect=WebSocketDisconnect()))
        memory = SimpleNamespace(total=100, used=60, percent=60)
        network = SimpleNamespace(bytes_sent=1, bytes_recv=2)
        sleep = AsyncMock()
        with patch.object(core.psutil, 'cpu_percent', side_effect=[RuntimeError('sample failed'), 12]), patch.object(core.psutil, 'virtual_memory', return_value=memory), patch.object(core.psutil, 'net_io_counters', return_value=network), patch.object(core.psutil, 'disk_partitions', return_value=[]), patch.object(core.asyncio, 'sleep', new=sleep), patch.object(core.logger, 'warning') as warning:
            await core.ws_sys_metrics(socket)
        socket.accept.assert_awaited_once()
        socket.send_json.assert_awaited_once()
        self.assertEqual([call.args for call in sleep.await_args_list], [(2,), (0.5,)])
        warning.assert_called_once()
