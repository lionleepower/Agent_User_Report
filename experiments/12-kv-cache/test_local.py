import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('kv_local', Path(__file__).with_name('local.py'))
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


class ObservationTests(unittest.TestCase):
    def test_missing_allocation_is_not_gpu_usage(self):
        self.assertIsNone(local.allocation('GPU memory used 4096 MiB'))
        self.assertEqual(local.allocation('llama_kv_cache: CUDA0 KV buffer size = 576.00 MiB'), 576)

    def test_exact_metric_name_does_not_mix_counters(self):
        text = 'llamacpp:prompt_tokens_total 42\nllamacpp:prompt_tokens_cached_total 99\n'
        self.assertEqual(local.metric(text, 'llamacpp:prompt_tokens_cached_total'), 99)
        self.assertIsNone(local.metric(text, 'KV_bytes'))


if __name__ == '__main__':
    unittest.main()
