"""Deterministic renderers for the service/dependency graph.

``to_dot`` emits Graphviz DOT (render it with ``dot -Tsvg``); ``to_svg`` emits a
self-contained, dependency-free layered SVG so the graph is viewable without
Graphviz installed. Both are fully deterministic: nodes and edges are sorted, so
the same model always produces byte-identical output.
"""

from __future__ import annotations

from .model import Graph

_NODE_STYLE = {
    "service": ("#1f6feb", "box"),
    "executable": ("#2ea043", "ellipse"),
    "external-library": ("#8957e5", "note"),
}
_EDGE_STYLE = {
    "requires": "solid",
    "after": "dashed",
    "wants": "dotted",
    "starts": "bold",
    "links": "solid",
    "crosses": "bold",
}


def _sorted_nodes(graph: Graph) -> list[dict]:
    return sorted(graph.nodes, key=lambda n: n["id"])


def _sorted_edges(graph: Graph):
    return sorted(graph.edges, key=lambda e: (e.src, e.dst, e.kind))


def to_dot(graph: Graph) -> str:
    lines = ["digraph blackglass {", "  rankdir=LR;", '  node [fontname="sans-serif", fontsize=10];']
    for node in _sorted_nodes(graph):
        color, shape = _NODE_STYLE.get(node["type"], ("#6e7681", "box"))
        label = node["label"].replace('"', "'")
        extra = ""
        if node["type"] == "executable" and node["attrs"].get("setuid"):
            extra = " [setuid]"
        if node["type"] == "external-library":
            extra = " [unresolved]"
        lines.append(f'  "{node["id"]}" [label="{label}{extra}", shape={shape}, color="{color}"];')
    for edge in _sorted_edges(graph):
        style = _EDGE_STYLE.get(edge.kind, "solid")
        color = "#d1242f" if edge.kind == "crosses" else "#57606a"
        lines.append(f'  "{edge.src}" -> "{edge.dst}" [label="{edge.kind}", style={style}, color="{color}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def to_svg(graph: Graph) -> str:
    columns = {"service": 0, "executable": 1, "external-library": 2}
    buckets: dict[int, list[dict]] = {0: [], 1: [], 2: []}
    for node in _sorted_nodes(graph):
        buckets[columns.get(node["type"], 1)].append(node)

    col_w, row_h, box_w, box_h, pad = 300, 70, 190, 34, 30
    positions: dict[str, tuple[int, int]] = {}
    height = pad * 2 + max((len(b) for b in buckets.values()), default=1) * row_h
    width = pad * 2 + 3 * col_w
    for col, nodes in buckets.items():
        for i, node in enumerate(nodes):
            x = pad + col * col_w
            y = pad + i * row_h
            positions[node["id"]] = (x, y)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif" font-size="11">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        '<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">'
        '<path d="M0,0 L7,3 L0,6 Z" fill="#57606a"/></marker></defs>',
    ]
    for edge in _sorted_edges(graph):
        if edge.src not in positions or edge.dst not in positions:
            continue
        x1, y1 = positions[edge.src]
        x2, y2 = positions[edge.dst]
        stroke = "#d1242f" if edge.kind == "crosses" else "#8c959f"
        dash = ' stroke-dasharray="4,3"' if edge.kind in ("after", "wants") else ""
        parts.append(
            f'<line x1="{x1 + box_w}" y1="{y1 + box_h // 2}" x2="{x2}" y2="{y2 + box_h // 2}" '
            f'stroke="{stroke}"{dash} marker-end="url(#a)"/>'
        )
    for node in _sorted_nodes(graph):
        x, y = positions[node["id"]]
        color, _ = _NODE_STYLE.get(node["type"], ("#6e7681", "box"))
        suffix = " ⚠" if node["type"] == "external-library" else ""
        if node["type"] == "executable" and node["attrs"].get("setuid"):
            suffix = " (setuid)"
        label = (node["label"] + suffix).replace("&", "&amp;").replace("<", "&lt;")
        parts.append(
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="5" '
            f'fill="#ffffff" stroke="{color}" stroke-width="1.5"/>'
        )
        parts.append(f'<text x="{x + 8}" y="{y + box_h // 2 + 4}" fill="#1f2328">{label[:30]}</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
