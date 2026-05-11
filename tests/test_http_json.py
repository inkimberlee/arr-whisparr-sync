"""Tests for http_json — request handling, retries, and response parsing."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from whisparr_sync import WhisparrError, http_json
from whisparr_sync import WhisparrScene, WhisparrStatistics


def _mock_response(status_code, json_data):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


def _patch_session(response):
    session = MagicMock()
    session.request.return_value = response
    return session


class TestHttpJson:
    def test_successful_get_returns_status_and_body(self):
        resp = _mock_response(200, {"id": 1, "title": "test"})
        with patch("whisparr_sync.requests.Session") as MockSession:
            MockSession.return_value.__enter__ = MagicMock()
            MockSession.return_value.request.return_value = resp
            MockSession.return_value.mount = MagicMock()
            status, body = http_json(
                method="GET",
                url="http://whisparr/api/v3/movie",
                api_key="testkey",
            )
        assert status == 200
        assert body == {"id": 1, "title": "test"}

    def test_parses_into_response_model(self):
        resp = _mock_response(200, {
            "title": "Test",
            "id": 1,
            "path": "/data",
            "statistics": {"movieFileCount": 0, "sizeOnDisk": 0},
        })
        with patch("whisparr_sync.requests.Session") as MockSession:
            MockSession.return_value.mount = MagicMock()
            MockSession.return_value.request.return_value = resp
            status, scene = http_json(
                method="GET",
                url="http://whisparr/api/v3/movie/1",
                api_key="testkey",
                response_model=WhisparrScene,
            )
        assert status == 200
        assert isinstance(scene, WhisparrScene)
        assert scene.id == 1

    def test_parses_list_response_model(self):
        resp = _mock_response(200, [
            {"title": "S1", "id": 1, "path": "/d", "statistics": {"movieFileCount": 0, "sizeOnDisk": 0}},
            {"title": "S2", "id": 2, "path": "/e", "statistics": {"movieFileCount": 0, "sizeOnDisk": 0}},
        ])
        with patch("whisparr_sync.requests.Session") as MockSession:
            MockSession.return_value.mount = MagicMock()
            MockSession.return_value.request.return_value = resp
            status, scenes = http_json(
                method="GET",
                url="http://whisparr/api/v3/movie",
                api_key="testkey",
                response_model=WhisparrScene,
                response_is_list=True,
            )
        assert len(scenes) == 2
        assert all(isinstance(s, WhisparrScene) for s in scenes)

    def test_raises_whisparr_error_on_4xx(self):
        resp = _mock_response(401, {"message": "unauthorized"})
        with patch("whisparr_sync.requests.Session") as MockSession:
            MockSession.return_value.mount = MagicMock()
            MockSession.return_value.request.return_value = resp
            with pytest.raises(WhisparrError, match="HTTP 401"):
                http_json(
                    method="GET",
                    url="http://whisparr/api/v3/movie",
                    api_key="badkey",
                )

    def test_raises_whisparr_error_on_5xx(self):
        resp = _mock_response(500, "internal error")
        with patch("whisparr_sync.requests.Session") as MockSession:
            MockSession.return_value.mount = MagicMock()
            MockSession.return_value.request.return_value = resp
            with pytest.raises(WhisparrError, match="HTTP 500"):
                http_json(method="GET", url="http://whisparr/api", api_key="k")

    def test_raises_whisparr_error_on_connection_error(self):
        with patch("whisparr_sync.requests.Session") as MockSession:
            MockSession.return_value.mount = MagicMock()
            MockSession.return_value.request.side_effect = requests.RequestException("conn refused")
            with pytest.raises(WhisparrError, match="HTTP request failed"):
                http_json(method="GET", url="http://bad-host/api", api_key="k")

    def test_handles_non_json_response(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.side_effect = ValueError("not json")
        resp.text = "plain text response"
        with patch("whisparr_sync.requests.Session") as MockSession:
            MockSession.return_value.mount = MagicMock()
            MockSession.return_value.request.return_value = resp
            status, body = http_json(method="GET", url="http://whisparr/api", api_key="k")
        assert status == 200
        assert body == "plain text response"

    def test_accepts_pydantic_model_as_body(self):
        """http_json should serialize a BaseModel body before sending."""
        resp = _mock_response(200, {})
        with patch("whisparr_sync.requests.Session") as MockSession:
            MockSession.return_value.mount = MagicMock()
            MockSession.return_value.request.return_value = resp
            from whisparr_sync import RefreshMovieCommand
            body = RefreshMovieCommand(movieIds=[1])
            http_json(method="POST", url="http://whisparr/api/v3/command", api_key="k", body=body)
            call_kwargs = MockSession.return_value.request.call_args.kwargs
            assert isinstance(call_kwargs["json"], dict)  # serialized, not raw model

    def test_returns_raw_when_model_parse_fails(self):
        """When response_model parsing raises, raw parsed body is returned."""
        resp = _mock_response(200, {"unexpected": "shape"})
        with patch("whisparr_sync.requests.Session") as MockSession:
            MockSession.return_value.mount = MagicMock()
            MockSession.return_value.request.return_value = resp
            status, body = http_json(
                method="GET",
                url="http://whisparr/api/v3/movie/1",
                api_key="k",
                response_model=WhisparrScene,  # missing required fields → parse fails
            )
        assert status == 200
        assert body == {"unexpected": "shape"}

    def test_dev_mode_logs_model_name(self):
        """dev=True path logs model name and raw data (lines 295-296)."""
        resp = _mock_response(200, {
            "title": "T", "id": 1, "path": "/d",
            "statistics": {"movieFileCount": 0, "sizeOnDisk": 0},
        })
        with patch("whisparr_sync.requests.Session") as MockSession:
            MockSession.return_value.mount = MagicMock()
            MockSession.return_value.request.return_value = resp
            status, scene = http_json(
                method="GET",
                url="http://whisparr/api/v3/movie/1",
                api_key="k",
                response_model=WhisparrScene,
                dev=True,
            )
        assert isinstance(scene, WhisparrScene)

    def test_sends_api_key_header(self):
        resp = _mock_response(200, {})
        with patch("whisparr_sync.requests.Session") as MockSession:
            MockSession.return_value.mount = MagicMock()
            MockSession.return_value.request.return_value = resp
            http_json(method="GET", url="http://whisparr/api", api_key="mykey123")
            call_kwargs = MockSession.return_value.request.call_args.kwargs
            assert call_kwargs["headers"]["X-Api-Key"] == "mykey123"
