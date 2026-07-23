import json

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


def test_llm_cache_persists_traceable_generation_record(tmp_path):
    cfg = Config(data_dir=tmp_path / "data", results_dir=tmp_path / "results", llm_backend="mock")
    cfg.ensure_dirs()
    first_client = LLMClient(cfg)
    first_client.generate("propose traceable factors", system="return json")
    first_record = first_client.generation_record()

    second_client = LLMClient(cfg)
    second_client.generate("propose traceable factors", system="return json")
    second_record = second_client.generation_record()

    assert first_record is not None
    assert second_record is not None
    assert first_record["generation_record_id"] == second_record["generation_record_id"]
    assert first_record["prompt_hash"] == second_record["prompt_hash"]
    assert first_record["output_hash"] == second_record["output_hash"]
    assert first_record["cache_hit"] is False
    assert second_record["cache_hit"] is True
    assert second_client.calls == 0
    persisted = json.loads(next((cfg.cache_dir / "llm").glob("*.json")).read_text(encoding="utf-8"))
    assert persisted["model"] == cfg.llm_model
    assert persisted["max_tokens"] == cfg.llm_max_tokens
