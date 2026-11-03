import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from aiohttp import ClientSession, web
from ai_web_mcp.bridge import SERVICE_KEY, create_app


class LatestWritingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        root = Path(__file__).resolve().parents[1] / 'temp'
        root.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=root)
        self.app = create_app({'host': '127.0.0.1', 'port': 0, 'bridge_token': 'fixture-token',
                               'database_path': str(Path(self.directory.name) / 'test.sqlite3')})
        self.store = self.app[SERVICE_KEY].store
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.base = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
        self.session = ClientSession(headers={'X-Bridge-Token': 'fixture-token'})

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()
        self.directory.cleanup()

    async def connect(self, generating=False):
        ws = await self.session.ws_connect(self.base.replace('http:', 'ws:') + '/ws/extension?token=fixture-token',
                                           headers={'Origin': 'chrome-extension://fixture'})
        await ws.receive_json()
        await ws.send_json({'type': 'hello', 'target_id': 'writing-tab', 'provider': 'chatgpt',
                            'conversation_id': 'writing-fixture', 'tab_bound': True, 'page_ready': True,
                            'tab_id': 1, 'tab_url': 'https://chatgpt.com/c/writing-fixture', 'generating': generating})
        while not self.app[SERVICE_KEY].targets.get('writing-tab'):
            await asyncio.sleep(0)
        return ws

    async def snapshot_latest(self, ws, messages, conversation='writing-fixture'):
        pending = asyncio.create_task(self.session.get(self.base + '/api/chat/latest',
            params={'conversation_id': 'writing-fixture', 'target_id': 'writing-tab'}))
        command = await asyncio.wait_for(ws.receive_json(), 1)
        self.assertEqual(command['type'], 'sync')
        await ws.send_json({'type': 'sync_result', 'request_id': command['request_id'],
                            'conversation_id': conversation, 'messages': messages})
        return await (await pending).json()

    async def test_cached_latest_ignores_late_user_and_observes_edited_assistant(self):
        self.store.append_message('writing-fixture', 'draft', 'assistant', '# Original', 'a', observed_at=1)
        self.store.append_message('writing-fixture', 'other', 'assistant', 'Other answer', 'b', observed_at=2)
        self.store.append_message('writing-fixture', 'old-user', 'user', 'Late old user', 'c', observed_at=4)
        self.store.append_message('writing-fixture', 'draft', 'assistant', '# Revised\n\nParagraph', 'd', observed_at=5)
        response = await self.session.get(self.base + '/api/chat/latest?conversation_id=writing-fixture')
        result = await response.json()
        self.assertEqual(result['message']['content'], '# Revised\n\nParagraph')
        self.assertEqual(result['message']['role'], 'assistant')
        self.assertEqual(result['source'], 'cache')

    async def test_live_writing_body_wins_over_database_insertion_order(self):
        self.store.append_message('writing-fixture', 'stale', 'assistant', 'Old cached answer', 'a')
        self.store.append_message('writing-fixture', 'old-user', 'user', 'Old question inserted late', 'b')
        ws = await self.connect()
        body = '# Article title\n\n## Subtitle\n\nFirst paragraph.\n\nLast paragraph.'
        result = await self.snapshot_latest(ws, [
            {'message_id': 'earlier', 'role': 'assistant', 'content': 'Earlier answer'},
            {'message_id': 'question', 'role': 'user', 'content': 'Write an article'},
            {'message_id': 'writing', 'role': 'assistant', 'content': body, 'kind': 'writing', 'content_format': 'markdown'},
            {'message_id': 'new-question', 'role': 'user', 'content': 'Follow up'},
        ])
        self.assertEqual(result['message']['content'], body)
        self.assertEqual(result['message']['kind'], 'writing')
        self.assertEqual(result['message']['content_format'], 'markdown')
        self.assertEqual(result['source'], 'live')
        self.assertEqual(self.store.get_message('writing-fixture', 'writing')['content'], body)
        await ws.close()

    async def test_empty_live_answer_is_not_replaced_with_old_cached_answer(self):
        self.store.append_message('writing-fixture', 'stale', 'assistant', 'Old cached answer', 'a')
        ws = await self.connect(generating=True)
        result = await self.snapshot_latest(ws, [{'message_id': 'user', 'role': 'user', 'content': 'Pending'}])
        self.assertIsNone(result['message'])
        self.assertEqual(result['source'], 'live')
        self.assertEqual(result['response_state'], 'streaming')
        await ws.close()

    async def test_history_page_waits_for_initial_empty_snapshot_to_hydrate(self):
        ws = await self.connect()
        pending = asyncio.create_task(self.session.get(self.base + '/api/chat/latest',
            params={'conversation_id': 'writing-fixture', 'target_id': 'writing-tab'}))
        first = await asyncio.wait_for(ws.receive_json(), 1)
        await ws.send_json({'type': 'sync_result', 'request_id': first['request_id'],
                            'conversation_id': 'writing-fixture', 'messages': []})
        second = await asyncio.wait_for(ws.receive_json(), 1)
        self.assertNotEqual(first['request_id'], second['request_id'])
        await ws.send_json({'type': 'sync_result', 'request_id': second['request_id'],
                            'conversation_id': 'writing-fixture', 'messages': [
                                {'message_id': 'writing', 'role': 'assistant', 'content': '# Loaded\n\nBody.'}]})
        result = await (await pending).json()
        self.assertEqual(result['source'], 'live')
        self.assertEqual(result['message']['content'], '# Loaded\n\nBody.')
        self.assertFalse(self.app[SERVICE_KEY].sync_waiters)
        await ws.close()

    async def test_still_loading_history_discloses_cache_fallback(self):
        self.store.append_message('writing-fixture', 'cached', 'assistant', '# Cached body', 'a')
        ws = await self.connect()
        with patch('ai_web_mcp.bridge.LATEST_SYNC_TIMEOUT', 0.2):
            result = await self.snapshot_latest(ws, [])
        self.assertEqual(result['source'], 'cache')
        self.assertEqual(result['sync_error'], 'PAGE_LOADING')
        self.assertEqual(result['message']['content'], '# Cached body')
        self.assertFalse(self.app[SERVICE_KEY].sync_waiters)
        await ws.close()

    async def test_page_navigation_discloses_cache_fallback_without_cross_conversation_write(self):
        self.store.append_message('writing-fixture', 'cached', 'assistant', 'Correct cached body', 'a')
        ws = await self.connect()
        result = await self.snapshot_latest(ws, [{'message_id': 'other', 'role': 'assistant', 'content': 'Wrong chat'}], 'other-conversation')
        self.assertEqual(result['source'], 'cache')
        self.assertEqual(result['sync_error'], 'CONVERSATION_MISMATCH')
        self.assertEqual(result['message']['content'], 'Correct cached body')
        self.assertIsNone(self.store.get_message('writing-fixture', 'other'))
        await ws.close()

    async def test_reload_without_page_refresh_preserves_writing_drafts(self):
        ws = await self.connect()
        pending = asyncio.create_task(self.session.post(self.base + '/api/reload-extension', json={'refresh_tab': False}))
        command = await asyncio.wait_for(ws.receive_json(), 1)
        self.assertEqual(command['type'], 'reload_extension')
        self.assertEqual(command['tab_id'], 0)
        self.assertTrue((await (await pending).json())['success'])
        await ws.close()
