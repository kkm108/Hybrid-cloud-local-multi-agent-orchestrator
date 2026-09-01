"""T08: Timer component scheduler tests (injectable clock, kill switch)."""

from socialai.orchestrator.timer import TimerScheduler


class FakeClock:
    """Deterministic clock controllable by tests."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, delta: float) -> None:
        self.now += delta


def _scheduler(clock: FakeClock, on_fire=None) -> TimerScheduler:
    return TimerScheduler(clock=clock, sleep=lambda _s: None, on_fire=on_fire)


class TestFiring:
    def test_fires_after_interval_to_assigned_ai(self) -> None:
        clock = FakeClock(0.0)
        fired: list[tuple[str, str, str]] = []

        def on_fire(ai: str, trigger: str) -> None:
            fired.append(("t1", ai, trigger))

        s = _scheduler(clock, on_fire)
        s.add("t1", interval_s=10.0, trigger="go now", assigned_ai="deepseek_1")

        # Before the interval, nothing fires.
        clock.advance(9.0)
        assert s.tick() == []

        # At/after the interval, exactly one fire.
        clock.advance(1.0)
        s.tick()
        assert fired == [("t1", "deepseek_1", "go now")]

    def test_repeats_every_interval(self) -> None:
        clock = FakeClock(0.0)
        fires: list[str] = []
        s = _scheduler(clock, lambda ai, tr: fires.append(tr))
        s.add("t1", interval_s=5.0, trigger="tick", assigned_ai="a_1")

        for step in range(3):
            clock.advance(5.0)
            s.tick()
        assert fires == ["tick", "tick", "tick"]

    def test_does_not_duplicate_when_far_past_due(self) -> None:
        clock = FakeClock(0.0)
        fires: list[str] = []
        s = _scheduler(clock, lambda ai, tr: fires.append(tr))
        s.add("t1", interval_s=5.0, trigger="tick", assigned_ai="a_1")

        clock.advance(50.0)  # 10 intervals skipped
        s.tick()
        # Only one fire, not ten (catch-up once).
        assert fires == ["tick"]

    def test_remove_stops_firing(self) -> None:
        clock = FakeClock(0.0)
        fires: list[str] = []
        s = _scheduler(clock, lambda ai, tr: fires.append(tr))
        s.add("t1", interval_s=5.0, trigger="tick", assigned_ai="a_1")
        s.remove("t1")
        clock.advance(5.0)
        s.tick()
        assert fires == []


class TestLifecycle:
    def test_stop_cancels_and_clears(self) -> None:
        clock = FakeClock(0.0)
        s = _scheduler(clock)
        s.add("t1", interval_s=5.0, trigger="x", assigned_ai="a_1")
        s.stop()
        assert s.timers == {}
        # stop() is safe to call again (idempotent kill switch).
        s.stop()

    def test_start_stop_thread_no_crash(self) -> None:
        s = TimerScheduler(clock=FakeClock(0.0), sleep=lambda _s: None)
        s.add("t1", interval_s=1.0, trigger="x", assigned_ai="a_1")
        s.start()
        s.stop()
        assert s._thread is None  # joined and cleared

    def test_stop_survives_callback_failure(self) -> None:
        def boom(ai, tr):
            raise RuntimeError("boom")

        clock = FakeClock(0.0)
        s = TimerScheduler(clock=clock, sleep=lambda _s: None, on_fire=boom)
        s.add("t1", interval_s=1.0, trigger="x", assigned_ai="a_1")
        clock.advance(1.0)
        # The loop guards callbacks; tick surfaces the error but stop still works.
        try:
            s.tick()
        except RuntimeError:
            pass
        s.stop()
        assert s.timers == {}


class TestRegistration:
    def test_add_schedules_next_fire_from_now(self) -> None:
        clock = FakeClock(100.0)
        s = _scheduler(clock)
        s.add("t1", interval_s=20.0, trigger="x", assigned_ai="a_1")
        assert s.timers["t1"]["next_fire"] == 120.0

    def test_clear_removes_all(self) -> None:
        s = _scheduler(FakeClock(0.0))
        s.add("t1", interval_s=1.0, trigger="x", assigned_ai="a_1")
        s.add("t2", interval_s=2.0, trigger="y", assigned_ai="a_2")
        s.clear()
        assert s.timers == {}
