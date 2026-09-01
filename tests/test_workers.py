"""T05: Worker-tab bridge tests (§2, busy/idle contract)."""

import time

import pytest

from socialai.workers.bridge import WorkerStatus
from socialai.workers.mock import MockWorker
from socialai.workers.playwright_adapter import PlaywrightAdapter, _load_selectors


class TestMockWorker:
    def test_scripted_reply_in_order(self) -> None:
        w = MockWorker("deepseek_1", script=["first", "second"])
        assert w.send("q1") == "first"
        assert w.send("q2") == "second"

    def test_fallback_reply_when_script_exhausted(self) -> None:
        w = MockWorker("gemini1_1")
        assert w.send("hello").startswith("mock:gemini1_1:")

    def test_send_records_last_message(self) -> None:
        w = MockWorker("chatgpt_1")
        w.send("prompt text")
        assert w.last_message == "prompt text"

    def test_read_returns_last_reply(self) -> None:
        w = MockWorker("chatgpt_1", script=["replyA"])
        assert w.send("x") == "replyA"
        assert w.read() == "replyA"

    def test_attach_sets_attached(self) -> None:
        w = MockWorker("deepseek_1")
        assert not w.attached
        assert w.attach() is True
        assert w.attached


class TestHeartbeat:
    def test_heartbeat_shape(self) -> None:
        w = MockWorker("deepseek_1")
        hb = w.heartbeat()
        assert hb["worker_id"] == "deepseek_1"
        assert hb["vendor"] == "mock"
        assert hb["status"] == "IDLE"
        assert hb["last_heartbeat"] == 0.0

    def test_heartbeat_after_send(self) -> None:
        w = MockWorker("deepseek_1")
        w.send("hi")
        hb = w.heartbeat()
        assert hb["status"] == "IDLE"
        assert hb["last_heartbeat"] > 0


class TestBusyIdleContract:
    def test_busy_during_processing_idle_after(self) -> None:
        captured: list[str] = []

        class CaptureWorker(MockWorker):
            def _send_impl(self, message: str) -> str:
                captured.append(self.status.value)
                time.sleep(0.01)
                return super()._send_impl(message)

        w = CaptureWorker("deepseek_1")
        assert w.status == WorkerStatus.IDLE
        w.send("go")
        # Inside processing it must have been BUSY.
        assert captured == ["BUSY"]
        assert w.status == WorkerStatus.IDLE


class TestSelectors:
    @pytest.mark.parametrize(
        "vendor,expect",
        [
            ("deepseek", ["input_box", "send_btn", "last_message"]),
            ("gemini", ["input_box", "send_btn", "last_message"]),
            ("chatgpt", ["input_box", "send_btn", "last_message"]),
        ],
    )
    def test_vendor_selectors_present(self, vendor, expect) -> None:
        sel = _load_selectors(vendor)
        for key in expect:
            assert key in sel
            assert sel[key]

    def test_unknown_vendor_returns_empty(self) -> None:
        assert _load_selectors("nonexistent") == {}


class TestPlaywrightAdapter:
    def test_selectors_loaded_per_vendor(self) -> None:
        a = PlaywrightAdapter("deepseek_1", "deepseek")
        assert a.selectors["input_box"]
        assert a.selectors["send_btn"]
        assert a.selectors["last_message"]

    def test_adapter_send_busy_then_idle(self) -> None:
        a = PlaywrightAdapter("gemini1_1", "gemini")
        assert a.status == WorkerStatus.IDLE
        result = a.send("hi")
        assert result.startswith("live:gemini1_1:")
        assert a.status == WorkerStatus.IDLE


@pytest.mark.live
def test_real_tab_send_live() -> None:
    """Real vendor tab drive — only runs with the ``live`` marker.

    Requires playwright installed (extra ``live``) and a signed-in chatgpt tab.
    """
    adapter = PlaywrightAdapter("chatgpt_1", "chatgpt")
    assert adapter.attach() is True
    reply = adapter.send("ping")
    assert reply  # a real reply from the live tab
    assert adapter.status == WorkerStatus.IDLE
