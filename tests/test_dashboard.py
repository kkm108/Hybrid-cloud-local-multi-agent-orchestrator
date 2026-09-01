"""T06/T17: Dashboard frontend render test (`ui` marker, STEP 0 census)."""

import pytest
from fastapi.testclient import TestClient

from socialai.orchestrator.app import build_app


@pytest.mark.ui
def test_dashboard_renders_at_root() -> None:
    app = build_app()
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "SocialAI Control Center" in r.text
