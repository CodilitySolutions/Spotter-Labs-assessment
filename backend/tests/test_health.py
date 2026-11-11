from django.test import Client


def test_health_returns_ok() -> None:
    response = Client().get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_ignores_unknown_host_but_other_endpoints_do_not(settings) -> None:
    """Platform health checks may use an internal hostname; everything else stays strict."""
    settings.DEBUG = False
    settings.ALLOWED_HOSTS = [".onrender.com"]
    client = Client(HTTP_HOST="10.0.0.5:10000")

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/geocode", {"q": "Denver"}).status_code == 400  # DisallowedHost
