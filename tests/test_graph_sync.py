"""方法依赖图的防漂移测试(PLATFORM_V2_SPEC §2.8 / ADR-0019)。

**方向不对称,这是壁垒在测试层的体现:**
只断言"图上的东西代码里有"(图 ⊆ 代码),**不断言反向**。
反向断言等于强制把所有代码实体都上图,直接违反 curation 原则 ——
图允许有意省略,不允许凭空捏造。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_DIR = REPO_ROOT / "platform"
sys.path.insert(0, str(PLATFORM_DIR))

import graph as graph_mod  # noqa: E402


@pytest.fixture(scope="module")
def g():
    return graph_mod.load_graph()


def test_graph_parses(g):
    """节点/边/层的引用完整性 —— load_graph 内部已校验,这里确认它真的跑通。"""
    assert g.nodes, "图里没有节点"
    assert g.edges, "图里没有边"
    layer_ids = set(g.layer_ids())
    for node_id, node in g.nodes.items():
        assert node["layer"] in layer_ids, f"{node_id} 的 layer 未定义"
    for edge in g.edges:
        assert edge["from"] in g.nodes and edge["to"] in g.nodes


def test_graph_is_dag(g):
    """有环会让"回溯上游"死循环。"""
    assert graph_mod.is_dag(g)


def test_operators_subset_of_engine(g):
    """图 ⊆ 代码:图上每个算子节点都必须真实注册在 FACTOR_FUNCTIONS 里。

    反向不查 —— 代码里有的算子允许不上图。
    """
    from src.factors.engine import FACTOR_FUNCTIONS

    registered = set(FACTOR_FUNCTIONS)
    for node_id, node in g.nodes.items():
        if node["layer"] != "operator":
            continue
        symbol = node.get("code_symbol")
        assert symbol, f"算子节点 {node_id} 缺 code_symbol"
        assert symbol in registered, (
            f"图上的算子 {symbol} 不在 FACTOR_FUNCTIONS 中(图捏造了不存在的算子)"
        )


def test_factor_nodes_match_baselines(g):
    """因子节点声明的 code_symbol 必须是真实存在的基线因子名。"""
    from src.factors.baseline import BASELINE_BY_NAME

    for node_id, node in g.nodes.items():
        if node["layer"] != "factor":
            continue
        symbol = node.get("code_symbol")
        if symbol is None:
            continue
        assert symbol in BASELINE_BY_NAME, f"图上的因子 {symbol} 不在 BASELINE_FACTORS 中"


def test_refs_exist(g):
    """每个节点引用的仓库路径都要真实存在,否则图会指向已删除的文件。"""
    missing = []
    for node_id, node in g.nodes.items():
        for ref in node.get("refs") or []:
            if not (REPO_ROOT / ref).exists():
                missing.append(f"{node_id} → {ref}")
    assert not missing, "图引用了不存在的路径:" + ", ".join(missing)


def test_layout_deterministic(g):
    """同一份 yaml 必须产出逐字节相同的 SVG,否则 git diff 失效、导出图不可复现。"""
    first = graph_mod.render_svg(g, graph_mod.layout(g))
    second = graph_mod.render_svg(g, graph_mod.layout(g))
    assert first == second


def test_no_factor_expressions(g):
    """红线:因子层只放类别与名称,不得泄漏具体表达式(ADR-0019 边界)。

    判据:因子节点的可见文本里不得出现"算子名 + 左括号"的组合。
    """
    from src.factors.engine import FACTOR_FUNCTIONS

    offenders = []
    for node_id, node in g.nodes.items():
        if node["layer"] != "factor":
            continue
        text = f"{node.get('label', '')} {node.get('one_liner', '')}"
        for op in FACTOR_FUNCTIONS:
            if f"{op}(" in text:
                offenders.append(f"{node_id} 含 {op}(")
    assert not offenders, "因子节点泄漏了表达式:" + ", ".join(offenders)


def test_every_metric_traces_to_a_field(g):
    """图存在的意义:每个评价指标都能一路回溯到原始字段。断言这条链没断。"""
    for node_id, node in g.nodes.items():
        if node["layer"] != "metric":
            continue
        anc = graph_mod.ancestors(g, node_id)
        fields = {a for a in anc if g.nodes[a]["layer"] == "field"}
        assert fields, f"指标 {node_id} 回溯不到任何原始字段 —— 可解释性链路断了"


def test_guards_attach_to_existing_nodes(g):
    for guard in g.guards:
        assert guard.get("attaches"), f"防线 {guard['id']} 没挂到任何节点"
        for target in guard["attaches"]:
            assert target in g.nodes
