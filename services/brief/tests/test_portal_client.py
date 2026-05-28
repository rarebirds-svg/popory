# popory_brief.portal_client: requests 래퍼 + exit code 매핑
import pytest
import responses

from popory_brief.portal_client import PortalClient, PortalError


@responses.activate
def test_get_success():
    responses.add(responses.GET, "https://api.popory.test/api/x",
                  json={"items": []}, status=200)
    c = PortalClient(base_url="https://api.popory.test", token_provider=lambda: "tok")
    body = c.get("/api/x")
    assert body == {"items": []}
    assert responses.calls[0].request.headers["Authorization"] == "Bearer tok"


@responses.activate
def test_get_401_maps_to_exit3():
    responses.add(responses.GET, "https://api.popory.test/api/x", status=401)
    c = PortalClient(base_url="https://api.popory.test", token_provider=lambda: "tok")
    with pytest.raises(PortalError) as ei:
        c.get("/api/x")
    assert ei.value.exit_code == 3


@responses.activate
def test_post_400_maps_to_exit4():
    responses.add(responses.POST, "https://api.popory.test/api/y",
                  json={"err": "bad"}, status=400)
    c = PortalClient(base_url="https://api.popory.test", token_provider=lambda: "tok")
    with pytest.raises(PortalError) as ei:
        c.post("/api/y", json={"a": 1})
    assert ei.value.exit_code == 4


@responses.activate
def test_post_500_retries_then_maps_to_exit5():
    responses.add(responses.POST, "https://api.popory.test/api/z", status=503)
    responses.add(responses.POST, "https://api.popory.test/api/z", status=503)
    c = PortalClient(base_url="https://api.popory.test", token_provider=lambda: "tok",
                     retry_backoff_seconds=0.0)
    with pytest.raises(PortalError) as ei:
        c.post("/api/z", json={})
    assert ei.value.exit_code == 5
    # 두 번 호출 (원호출 + 재시도 1회)
    assert len(responses.calls) == 2
