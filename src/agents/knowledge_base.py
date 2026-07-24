from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_KNOWLEDGE_PATH = Path(__file__).resolve().parents[2] / "knowledge" / "a_share" / "v1.json"
REQUIRED_SOURCE_KEYS = {
    "source_id",
    "title",
    "source_type",
    "url",
    "locator",
    "accessed_on",
    "coverage",
    "usage_boundary",
    "license",
}
REQUIRED_FIELD_KEYS = {
    "field",
    "label",
    "source_id",
    "source_table",
    "object_level",
    "frequency",
    "available_date",
    "pit_rule",
    "backtestable",
    "usage_boundary",
    "risks",
}


class KnowledgeValidationError(ValueError):
    pass


def _require_unique(records: list[dict[str, Any]], key: str, section: str) -> None:
    values = [record.get(key) for record in records]
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise KnowledgeValidationError(f"{section}.{key} must be a non-empty string")
    if len(values) != len(set(values)):
        raise KnowledgeValidationError(f"duplicate {section}.{key}")


def validate_knowledge_base(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise KnowledgeValidationError("knowledge base root must be an object")
    required_root = {
        "schema_version",
        "knowledge_version",
        "scope",
        "sources",
        "fields",
        "factor_priors",
        "institution_rules",
    }
    missing_root = required_root - set(data)
    if missing_root:
        raise KnowledgeValidationError(f"knowledge base missing keys: {sorted(missing_root)}")
    if data["schema_version"] != "1.0":
        raise KnowledgeValidationError(f"unsupported knowledge schema: {data['schema_version']}")
    for section in ("sources", "fields", "factor_priors", "institution_rules"):
        if not isinstance(data[section], list) or not data[section]:
            raise KnowledgeValidationError(f"knowledge base {section} must be a non-empty list")

    sources = data["sources"]
    fields = data["fields"]
    _require_unique(sources, "source_id", "sources")
    _require_unique(fields, "field", "fields")
    source_ids = {source["source_id"] for source in sources}
    for source in sources:
        missing = REQUIRED_SOURCE_KEYS - set(source)
        if missing:
            raise KnowledgeValidationError(f"source {source.get('source_id')} missing keys: {sorted(missing)}")
    for field in fields:
        missing = REQUIRED_FIELD_KEYS - set(field)
        if missing:
            raise KnowledgeValidationError(f"field {field.get('field')} missing keys: {sorted(missing)}")
        if field["source_id"] not in source_ids:
            raise KnowledgeValidationError(f"field {field['field']} references unknown source {field['source_id']}")
        if not isinstance(field["backtestable"], bool):
            raise KnowledgeValidationError(f"field {field['field']} backtestable must be boolean")
        if not isinstance(field["risks"], list):
            raise KnowledgeValidationError(f"field {field['field']} risks must be a list")

    for section, id_key in (("factor_priors", "prior_id"), ("institution_rules", "rule_id")):
        _require_unique(data[section], id_key, section)
        for record in data[section]:
            citations = record.get("citations")
            if not isinstance(citations, list) or not citations:
                raise KnowledgeValidationError(f"{section}.{record[id_key]} must contain citations")
            unknown = set(citations) - source_ids
            if unknown:
                raise KnowledgeValidationError(
                    f"{section}.{record[id_key]} references unknown sources: {sorted(unknown)}"
                )
    return data


@lru_cache(maxsize=4)
def load_knowledge_base(path: str | Path = DEFAULT_KNOWLEDGE_PATH) -> dict[str, Any]:
    resolved = Path(path).resolve()
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KnowledgeValidationError(f"cannot load knowledge base {resolved}: {exc}") from exc
    return validate_knowledge_base(data)


def source_index(knowledge: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    knowledge = knowledge or load_knowledge_base()
    return {item["source_id"]: item for item in knowledge["sources"]}


def field_index(knowledge: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    knowledge = knowledge or load_knowledge_base()
    return {item["field"]: item for item in knowledge["fields"]}


def validate_backtestable_claim(
    fields: set[str],
    metadata: dict[str, Any],
    knowledge: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    if metadata.get("backtestable_status") != "currently_backtestable":
        return True, "ok"
    knowledge = knowledge or load_knowledge_base()
    fields_by_name = field_index(knowledge)
    unavailable = sorted(
        field for field in fields if field not in fields_by_name or not fields_by_name[field]["backtestable"]
    )
    if unavailable:
        return False, f"fields are not registered as backtestable in the knowledge base: {unavailable}"

    citations = metadata.get("knowledge_citations")
    if not isinstance(citations, list) or not citations:
        return False, "currently_backtestable candidates must include knowledge_citations"
    source_ids = set(source_index(knowledge))
    unknown_citations = sorted(set(citations) - source_ids)
    if unknown_citations:
        return False, f"candidate references unknown knowledge sources: {unknown_citations}"
    required_sources = {fields_by_name[field]["source_id"] for field in fields}
    missing_citations = sorted(required_sources - set(citations))
    if missing_citations:
        return False, f"candidate does not cite field sources: {missing_citations}"
    return True, "ok"
