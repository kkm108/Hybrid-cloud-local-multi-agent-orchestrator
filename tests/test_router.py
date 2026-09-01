"""T02: Router dispatch + dead-letter tests (§2, §5)."""

import json

from socialai.protocol import Block
from socialai.router import Router


class TestDispatch:
    def test_registered_handler_is_called(self, tmp_path) -> None:
        router = Router(log_path=tmp_path / "routing.jsonl")
        calls: list[str] = []

        def handler(block: Block, from_id: str) -> str:
            calls.append(block.body)
            return f"handled:{block.body}"

        router.register("worker_1", handler)
        reply = router.dispatch_block(Block(target="worker_1", body="hi"), "router")
        assert reply == "handled:hi"
        assert calls == ["hi"]

    def test_routes_text_with_multiple_blocks(self, tmp_path) -> None:
        router = Router(log_path=tmp_path / "routing.jsonl")
        seen: list[str] = []

        def handler(block: Block, from_id: str) -> str:
            seen.append(block.target)
            return "ok"

        for cid in ("a_1", "b_1", "a_1"):
            router.register(cid, handler)

        router.dispatch_text(
            "[SEND_TO: a_1] x [/SEND_TO] [SEND_TO: b_1] y [/SEND_TO] "
            "[SEND_TO: a_1] z [/SEND_TO]"
        )
        assert seen == ["a_1", "b_1", "a_1"]


class TestUnknownTarget:
    def test_unknown_target_dead_lettered_no_crash(self, tmp_path) -> None:
        log = tmp_path / "routing.jsonl"
        router = Router(log_path=log)

        # No handlers registered, so every target is unknown.
        reply = router.dispatch_block(Block(target="ghost_9", body="hi"), "origin")
        assert reply is None

        lines = (log.read_text(encoding="utf-8")).strip().splitlines()
        assert lines, "expected at least one routing log line"
        last = json.loads(lines[-1])
        assert last["event"] == "dead_letter"
        assert last["to"] == "ghost_9"
        assert last["from"] == "origin"


class TestRoutingLog:
    def test_every_hop_is_logged(self, tmp_path) -> None:
        log = tmp_path / "routing.jsonl"
        router = Router(log_path=log)

        def handler(block: Block, from_id: str) -> str:
            return "ok"

        router.register("w_1", handler)
        router.dispatch_block(Block(target="w_1", body="go", verb="START_WORK"), "sender")

        lines = (log.read_text(encoding="utf-8")).strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["from"] == "sender"
        assert record["to"] == "w_1"
        assert record["verb"] == "START_WORK"
        assert len(record["hash"]) >= 8
