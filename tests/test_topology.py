"""T15: Query Topology view tests (nodes/edges aggregation + SVG page)."""

import json

import pytest
from fastapi.testclient import TestClient

from socialai import state as state_mod
from socialai.orchestrator.app import build_app
from socialai.orchestrator.topology import build_topology
from socialai.router import Router

FIXTURE_LOG = [
    {"from": "timer", "to": "deepseek_1", "ts": 1.0},
    {"from": "deepseek_1", "to": "chatgpt_1", "ts": 2.0},
    {"from": "chatgpt_1", "to": "gemini1_1", "ts": 3.0},
    {"from": "gemini1_1", "to": "facebook_post", "ts": 4.0},
    {"from": "timer", "to": "deepseek_1", "ts": 5.0},
]
# dead-letter entry (has from/to) is included in the aggregate
FIXTURE_LOG.append({"from": "timer", "to": "ghost_1", "ts": 6.0})

NODES_EXPECTED = [
    {"id": "chatgpt_1", "count": 2},
    {"id": "deepseek_1", "count": 3},
    {"id": "facebook_post", "count": 1},
    {"id": "gemini1_1", "count": 2},
    {"id": "ghost_1", "count": 1},
    {"id": "timer", "count": 3},
]

EDGES_EXPECTED = [
    {"from": "chatgpt_1", "to": "gemini1_1", "count": 1, "last_ts": 3.0},
    {"from": "deepseek_1", "to": "chatgpt_1", "count": 1, "last_ts": 2.0},
    {"from": "gemini1_1", "to": "facebook_post", "count": 1, "last_ts": 4.0},
    {"from": "timer", "to": "deepseek_1", "count": 2, "last_ts": 5.0},
    {"from": "timer", "to": "ghost_1", "count": 1, "last_ts": 6.0},
]


def _write_log(path) -> None:
    path.write_text(
        "\n".join(json.dumps(e) for e in FIXTURE_LOG) + "\n", encoding="utf-8"
    )


class TestBuildTopology:
    def test_exact_node_and_edge_counts_from_fixture(self, tmp_path) -> None:
        log = tmp_path / "routing.jsonl"
        _write_log(log)
        topo = build_topology(log)
        assert topo == {
            "nodes": NODES_EXPECTED,
            "edges": EDGES_EXPECTED,
        }

    def test_missing_log_is_empty_topology(self, tmp_path) -> None:
        assert build_topology(tmp_path / "nope.jsonl") == {"nodes": [], "edges": []}

    def test_garbage_lines_skipped(self, tmp_path) -> None:
        log = tmp_path / "routing.jsonl"
        log.write_text("not-json\n{'bad': json}\n", encoding="utf-8")
        assert build_topology(log) == {"nodes": [], "edges": []}


class TestTopologyApi:
    @pytest.fixture
    def client(self, tmp_path):
        state_mod.set_state_dir(tmp_path / "state")
        log = tmp_path / "routing.jsonl"
        _write_log(log)
        app = build_app(router=Router(log_path=log))
        with TestClient(app) as c:
            yield c

    def test_api_topology_exact_counts(self, client) -> None:
        r = client.get("/api/topology")
        assert r.status_code == 200
        assert r.json() == {"nodes": NODES_EXPECTED, "edges": EDGES_EXPECTED}

    @pytest.mark.ui
    def test_topology_page_renders_graph(self, client) -> None:
        r = client.get("/topology")
        assert r.status_code == 200
        text = r.text
        assert "Query Topology" in text
        assert "<svg" in text
        assert "timer" in text
        assert "facebook_post" in text
        assert "×3" in text  # timer count badge rendered
