"""方法依赖图 —— 加载 graph.yaml,做分层布局,渲染成静态内联 SVG(ADR-0019)。

为什么不用 d3/cytoscape:
  1. 站点是单文件自包含 HTML,内联一个图库(d3 ~270KB)为一张 40 节点的图不值。
  2. **这是分层 DAG,力导向布局会把层次甩成一坨抖动的毛球** —— 恰好毁掉要展示的东西。

布局是确定性的(平局按 id 字典序打破),同一份 yaml 每次构建产出逐字节相同的 SVG,
git diff 才有意义,导出给 PPT/论文的图也才可复现。
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field as dc_field
from pathlib import Path

import yaml

GRAPH_FILE = Path(__file__).resolve().parent / "content" / "graph.yaml"

# 版面常数
NODE_W = 168
NODE_H = 34
COL_GAP = 64
ROW_GAP = 12
MARGIN_X = 26
MARGIN_TOP = 54          # 给层标题留的高度
MARGIN_BOTTOM = 26
ROW_PITCH = NODE_H + ROW_GAP
COL_PITCH = NODE_W + COL_GAP

# 每层一个色相(HSL 的 H),深浅由 CSS 变量控制
LAYER_HUE = {"field": 190, "align": 210, "operator": 258, "factor": 285, "metric": 320}

EDGE_STYLE = {
    "computes": {"opacity": 0.34, "width": 1.2, "dash": ""},
    "uses": {"opacity": 0.22, "width": 1.0, "dash": "3 4"},
    "derives": {"opacity": 0.46, "width": 1.6, "dash": ""},
}


@dataclass
class Graph:
    layers: list[dict]
    nodes: dict[str, dict]
    edges: list[dict]
    guards: list[dict]
    order: list[str] = dc_field(default_factory=list)  # yaml 中的原始顺序,布局初值

    def layer_ids(self) -> list[str]:
        return [layer["id"] for layer in self.layers]

    def nodes_in(self, layer_id: str) -> list[str]:
        return [n for n in self.order if self.nodes[n]["layer"] == layer_id]

    def preds(self, node_id: str) -> list[str]:
        return [e["from"] for e in self.edges if e["to"] == node_id]

    def succs(self, node_id: str) -> list[str]:
        return [e["to"] for e in self.edges if e["from"] == node_id]

    def guards_of(self, node_id: str) -> list[dict]:
        return [g for g in self.guards if node_id in (g.get("attaches") or [])]


def load_graph(path: Path = GRAPH_FILE) -> Graph:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    layers = raw.get("layers") or []
    nodes = {n["id"]: n for n in (raw.get("nodes") or [])}
    order = [n["id"] for n in (raw.get("nodes") or [])]
    edges = raw.get("edges") or []
    guards = raw.get("guards") or []

    layer_ids = {layer["id"] for layer in layers}
    for node_id, node in nodes.items():
        if node.get("layer") not in layer_ids:
            raise ValueError(f"节点 {node_id} 的 layer={node.get('layer')} 不在 layers 中")
    for edge in edges:
        for side in ("from", "to"):
            if edge[side] not in nodes:
                raise ValueError(f"边 {edge} 的 {side}={edge[side]} 不是已定义节点")
    for guard in guards:
        for target in guard.get("attaches") or []:
            if target not in nodes:
                raise ValueError(f"防线 {guard['id']} attaches 到未定义节点 {target}")

    return Graph(layers=layers, nodes=nodes, edges=edges, guards=guards, order=order)


def is_dag(graph: Graph) -> bool:
    """回溯要沿边反向做传递闭包,有环会死循环 —— 构建期就拦住。"""
    color: dict[str, int] = {}

    def visit(node_id: str) -> bool:
        if color.get(node_id) == 1:
            return False
        if color.get(node_id) == 2:
            return True
        color[node_id] = 1
        for nxt in graph.succs(node_id):
            if not visit(nxt):
                return False
        color[node_id] = 2
        return True

    return all(visit(n) for n in graph.order)


def ancestors(graph: Graph, node_id: str) -> set[str]:
    """全部上游祖先 —— "一路回溯到原始字段"就是这个集合。"""
    seen: set[str] = set()
    stack = list(graph.preds(node_id))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(graph.preds(cur))
    return seen


def layout(graph: Graph) -> dict:
    """分层 + 重心法排序。平局按 id 字典序 → 输出完全确定。"""
    layer_ids = graph.layer_ids()
    columns = {lid: graph.nodes_in(lid) for lid in layer_ids}

    def barycenter(node_id: str, neighbours: list[str], ref: dict[str, int]) -> float:
        vals = [ref[n] for n in neighbours if n in ref]
        return sum(vals) / len(vals) if vals else -1.0

    for _ in range(2):
        # 正向:按前驱位置排后面的层
        index: dict[str, int] = {}
        for lid in layer_ids:
            for i, n in enumerate(columns[lid]):
                index[n] = i
        for lid in layer_ids[1:]:
            columns[lid] = sorted(
                columns[lid],
                key=lambda n: (barycenter(n, graph.preds(n), index), n),
            )
            for i, n in enumerate(columns[lid]):
                index[n] = i
        # 反向:按后继位置排前面的层
        for lid in reversed(layer_ids[:-1]):
            columns[lid] = sorted(
                columns[lid],
                key=lambda n: (barycenter(n, graph.succs(n), index), n),
            )
            for i, n in enumerate(columns[lid]):
                index[n] = i

    rows_max = max((len(v) for v in columns.values()), default=1)
    width = MARGIN_X * 2 + len(layer_ids) * NODE_W + (len(layer_ids) - 1) * COL_GAP
    height = MARGIN_TOP + rows_max * ROW_PITCH - ROW_GAP + MARGIN_BOTTOM

    pos: dict[str, tuple[float, float]] = {}
    for col, lid in enumerate(layer_ids):
        members = columns[lid]
        block_h = len(members) * ROW_PITCH - ROW_GAP
        top = MARGIN_TOP + (rows_max * ROW_PITCH - ROW_GAP - block_h) / 2
        x = MARGIN_X + col * COL_PITCH
        for row, node_id in enumerate(members):
            pos[node_id] = (x, top + row * ROW_PITCH)

    return {"pos": pos, "columns": columns, "width": width, "height": height}


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _edge_path(src: tuple[float, float], dst: tuple[float, float]) -> str:
    x1, y1 = src[0] + NODE_W, src[1] + NODE_H / 2
    x2, y2 = dst[0], dst[1] + NODE_H / 2
    cx = (x1 + x2) / 2
    return f"M{x1:.1f},{y1:.1f} C{cx:.1f},{y1:.1f} {cx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"


def render_svg(graph: Graph, laid: dict, standalone: bool = False, theme: str = "dark") -> str:
    pos = laid["pos"]
    width, height = laid["width"], laid["height"]

    ink = "#eef0fa" if theme == "dark" else "#12131c"
    faint = "#656b86" if theme == "dark" else "#8a8fa6"
    bg = "#06070e" if theme == "dark" else "#ffffff"
    lum = 62 if theme == "dark" else 44

    # 层标题
    heads = []
    for col, layer in enumerate(graph.layers):
        x = MARGIN_X + col * COL_PITCH + NODE_W / 2
        hue = LAYER_HUE.get(layer["id"], 220)
        heads.append(
            f'<text class="g-layer" x="{x:.1f}" y="24" text-anchor="middle" '
            f'fill="hsl({hue} 70% {lum}%)">{_esc(layer["label"])}</text>'
        )
        if layer.get("note"):
            heads.append(
                f'<text class="g-note" x="{x:.1f}" y="39" text-anchor="middle" '
                f'fill="{faint}">{_esc(layer["note"])}</text>'
            )

    # 边(先画,压在节点下面)
    edge_els = []
    for i, edge in enumerate(graph.edges):
        src, dst = pos[edge["from"]], pos[edge["to"]]
        style = EDGE_STYLE.get(edge.get("kind", "computes"), EDGE_STYLE["computes"])
        hue = LAYER_HUE.get(graph.nodes[edge["from"]]["layer"], 220)
        dash = f' stroke-dasharray="{style["dash"]}"' if style["dash"] else ""
        edge_els.append(
            f'<path class="g-edge" id="e{i}" data-from="{_esc(edge["from"])}" '
            f'data-to="{_esc(edge["to"])}" data-kind="{_esc(edge.get("kind", "computes"))}" '
            f'd="{_edge_path(src, dst)}" fill="none" stroke="hsl({hue} 70% {lum}%)" '
            f'stroke-width="{style["width"]}" stroke-opacity="{style["opacity"]}"{dash}/>'
        )

    # 节点
    node_els = []
    for node_id in graph.order:
        node = graph.nodes[node_id]
        x, y = pos[node_id]
        hue = LAYER_HUE.get(node["layer"], 220)
        emph = bool(node.get("emphasis"))
        guards = graph.guards_of(node_id)
        fill_a = ".18" if emph else ".09"
        stroke_a = ".70" if emph else ".38"
        label = _esc(node.get("label", node_id))
        # 有防线的节点右上角一个点;详情在回溯面板里列出
        dot = (
            f'<circle class="g-guarddot" cx="{x + NODE_W - 9:.1f}" cy="{y + 9:.1f}" r="3" '
            f'fill="hsl(190 90% 60%)"/>'
            if guards
            else ""
        )
        node_els.append(
            f'<g class="g-node{" emph" if emph else ""}" data-node="{_esc(node_id)}" '
            f'data-layer="{_esc(node["layer"])}" tabindex="0" role="button">'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{NODE_W}" height="{NODE_H}" rx="9" '
            f'fill="hsl({hue} 70% 50% / {fill_a})" stroke="hsl({hue} 70% {lum}% / {stroke_a})"/>'
            f'{dot}'
            f'<text x="{x + NODE_W / 2:.1f}" y="{y + NODE_H / 2 + 4:.1f}" text-anchor="middle" '
            f'fill="{ink}">{label}</text>'
            "</g>"
        )

    style_block = f"""<style>
  .g-layer {{ font: 700 12.5px var(--sans, system-ui); letter-spacing:.04em; }}
  .g-note  {{ font: 10.5px var(--sans, system-ui); }}
  .g-node text {{ font: 11.5px var(--mono, ui-monospace, Menlo, monospace); pointer-events:none; }}
  .g-node {{ cursor: pointer; }}
  .g-node rect {{ transition: fill .18s, stroke .18s; }}
  .g-node:hover rect, .g-node:focus rect {{ stroke-width: 1.8; }}
  .g-node:focus {{ outline: none; }}
  .dim {{ opacity: .12; }}
  .lit rect {{ stroke-width: 1.8; }}
  .g-edge.lit {{ stroke-opacity: .95 !important; stroke-width: 2 !important; }}
</style>"""

    open_tag = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}">'
        if standalone
        else f'<svg id="graph-svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="方法依赖图:从原始字段到评价指标的计算依赖">'
    )
    bg_rect = f'<rect width="{width}" height="{height}" fill="{bg}"/>' if standalone else ""

    return (
        open_tag
        + style_block
        + bg_rect
        + "".join(heads)
        + '<g class="g-edges">'
        + "".join(edge_els)
        + "</g><g class='g-nodes'>"
        + "".join(node_els)
        + "</g></svg>"
    )


def node_payload(graph: Graph) -> dict:
    """喂给前端 JS 的数据:回溯面板要用的一句话解释、防线、refs、层次。"""
    layer_label = {layer["id"]: layer["label"] for layer in graph.layers}
    return {
        "layers": [layer["id"] for layer in graph.layers],
        "layerLabels": layer_label,
        "nodes": {
            node_id: {
                "label": node.get("label", node_id),
                "layer": node["layer"],
                "one": node.get("one_liner", ""),
                "refs": node.get("refs", []),
                "guards": [
                    {"label": g["label"], "one": g.get("one_liner", "")}
                    for g in graph.guards_of(node_id)
                ],
            }
            for node_id, node in graph.nodes.items()
        },
        "edges": [{"f": e["from"], "t": e["to"], "k": e.get("kind", "computes")} for e in graph.edges],
    }
