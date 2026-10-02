"""Synthetic SDK tool tests: no network, credentials or corpus access."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('adapter', Path(__file__).with_name('adapter.py'))
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class TreeTests(unittest.TestCase):
    def run_search(self, replies, tool_result=None):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            (raw / 'pageindex-id.json').write_text('{"doc_id":"synthetic"}')
            (raw / 'public-input.json').write_text(json.dumps({'chunks': [{'id': 'c1', 'docName': 'public', 'text': 'synthetic'}]}))
            (raw / 'page-map.json').write_text('[{"id":"c1","pages":[1]}]')
            pi = types.SimpleNamespace(as_openai_tools=lambda **kw: [])
            module = types.ModuleType('pageindex.agent_tools')
            module.call_tool = lambda *a, **kw: (json.dumps(tool_result or {'page_index': 1}), False)
            with patch.dict(sys.modules, {'pageindex.agent_tools': module}), patch.dict(adapter.os.environ, {'BENCH_LLM_MODEL': 'mock'}), patch.object(adapter, 'request', side_effect=replies):
                return adapter.controlled(pi, raw, 'synthetic question')

    def test_unread_or_nonexistent_node_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'unread evidence'):
            self.run_search([{'choices': [{'message': {'content': '{"evidence_ids":["missing"]}'}}]}])

    def test_empty_evidence_is_recorded(self):
        self.assertEqual(self.run_search([{'choices': [{'message': {'content': '{"evidence_ids":[]}'}}]}])['ids'], [])

    def test_call_limit(self):
        tool = {'choices': [{'message': {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'tool', 'function': {'name': 'get_document_structure', 'arguments': '{}'}}]}}]}
        with self.assertRaisesRegex(RuntimeError, 'call limit'):
            self.run_search([tool] * 6)

    def test_only_read_pages_can_be_selected(self):
        tool = {'choices': [{'message': {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'tool', 'function': {'name': 'get_page_content', 'arguments': '{"pages":[1]}'}}]}}]}
        final = {'choices': [{'message': {'content': '{"evidence_ids":["c1"]}'}}]}
        self.assertEqual(self.run_search([tool, final])['ids'], ['c1'])


class NativeTraceTests(unittest.TestCase):
    def test_native_page_reads_are_counted_from_tool_envelopes(self):
        tools = types.ModuleType('pageindex.agent_tools')
        page = lambda client, **kw: ({'result': {'content': [{'page': 2, 'text': 'abc'}, {'page': 3, 'text': 'de'}]}}, False)
        failed = lambda client, **kw: ({'error': 'x'}, True)
        tools._IMPLEMENTATIONS = {'browse_documents': failed, 'get_document': failed, 'get_document_structure': failed, 'get_page_content': page}
        package = types.ModuleType('pageindex')
        package.agent_tools = tools
        with patch.dict(sys.modules, {'pageindex': package, 'pageindex.agent_tools': tools}):
            trace = adapter.observe_tools()
            tools._IMPLEMENTATIONS['get_document_structure'](None, doc_name='d')
            tools._IMPLEMENTATIONS['get_page_content'](None, doc_name='d', pages='2-3', _allowed_ids=frozenset())
        self.assertEqual([t['tool'] for t in trace], ['get_document_structure', 'get_page_content'])
        self.assertEqual(trace[1]['pages'], [2, 3])
        self.assertEqual(trace[1]['chars'], 5)
        self.assertNotIn('_allowed_ids', trace[1]['arguments'])
        self.assertTrue(trace[0]['error'])


class RetryTests(unittest.TestCase):
    def test_gateway_stops_are_final_for_sdk_retries(self):
        utils = types.ModuleType('pageindex.utils')
        utils._UNRECOVERABLE_STATUS = frozenset({401, 403, 404})
        package = types.ModuleType('pageindex')
        package.utils = utils
        with patch.dict(sys.modules, {'pageindex': package, 'pageindex.utils': utils}):
            adapter.harden()
        self.assertTrue({402, 503, 401}.issubset(utils._UNRECOVERABLE_STATUS))
        self.assertNotIn(429, utils._UNRECOVERABLE_STATUS)

    def test_backend_disables_sdk_retries(self):
        with patch.dict(adapter.os.environ, {'BENCH_GATE_TOKEN': 'synthetic', 'BENCH_LLM_BASE': 'http://127.0.0.1:1/x'}):
            self.assertEqual(adapter.backend()['max_retries'], 0)


if __name__ == '__main__':
    unittest.main()
