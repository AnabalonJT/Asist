"""Tests for main FastAPI application initialization."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    return TestClient(app)


def test_root_endpoint(client):
    """Test that the root endpoint returns the expected response."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "HabitTrack API"
    assert data["status"] == "running"
    assert "version" in data


def test_health_check_endpoint(client):
    """Test that the health check endpoint returns a response."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "database" in data


def test_cors_middleware_configured(client):
    """Test that CORS middleware is properly configured."""
    response = client.options(
        "/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        }
    )
    assert response.status_code in [200, 204]
