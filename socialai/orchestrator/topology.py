"""Query Topology aggregation (T15).

Reads ``state/logs/routing.jsonl`` and aggregates every hop into a graph:

    {"nodes": [{"id", "count"}],
     "edges": [{"from", "to", "count", "last_ts"}]}

A hop is any routing record carrying ``from`` and ``to`` (normal and
dead-letter entries alike). Node ``count`` is how many times the component
appears as either a sender or a target; edge ``count`` is the number of hops
between that (from, to) pair.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def build_topology(log_path: Path | None = None) -> dict:
    """Aggregate a routing jsonl file into a nodes/edges topology dict."""
    edge_counts: dict[tuple[str, str], int] = defaultdict(int)
    edge_last_ts: dict[tuple[str, str], float] = defaultdict(float)
    node_counts: dict[str, int] = defaultdict(int)

    if log_path is not None and Path(log_path).is_file():
        for line in Path(log_path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            src = record.get("from")
            dst = record.get("to")
            if src is None or dst is None:
                continue
            key = (src, dst)
            edge_counts[key] += 1
            last_ts = record.get("ts", 0.0)
            if last_ts > edge_last_ts[key]:
                edge_last_ts[key] = last_ts
            node_counts[src] += 1
            node_counts[dst] += 1

    nodes = [
        {"id": node_id, "count": node_counts[node_id]}
        for node_id in sorted(node_counts)
    ]
    edges = [
        {
            "from": src,
            "to": dst,
            "count": edge_counts[(src, dst)],
            "last_ts": edge_last_ts[(src, dst)],
        }
        for src, dst in sorted(edge_counts)
    ]
    return {"nodes": nodes, "edges": edges}
