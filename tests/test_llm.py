from src.config import Config
from src.llm.client import LLMClient


def test_llm_cache_hits_do_not_repeat_calls(tmp_path):
    cfg = Config(data_dir=tmp_path / "data", results_dir=tmp_path / "results", llm_backend="mock")
    cfg.ensure_dirs()
    client = LLMClient(cfg)
    first = client.generate("propose factors")
    second = client.generate("propose factors")
    assert first == second
    assert client.calls == 1
