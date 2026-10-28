"""
EGSI Endpoint Regression Tests

Tests for EGSI-M API endpoints to ensure route stability and correct responses.
"""
import pytest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.egsi import routes


@pytest.fixture
def client(monkeypatch):
    """Exercise the real ASGI router without startup jobs, sockets or DB writes."""
    row = {"date": date(2026, 10, 23), "value": 20, "band": "LOW",
           "region": "middle_east", "components": {}, "trend_1d": 1, "trend_7d": 2}
    monkeypatch.setattr(routes, "ENABLE_EGSI", True)
    monkeypatch.setattr(routes, "get_egsi_m_status", lambda: {
        "enabled": True, "model_version": "egsi_m_v1", "latest": row})
    for name in ("get_egsi_m_delayed_hours", "get_egsi_m_latest", "get_egsi_m_for_date"):
        monkeypatch.setattr(routes, name, lambda *a, **k: dict(row))
    monkeypatch.setattr(routes, "get_egsi_m_history", lambda **k: [dict(row)])
    compute = Mock(return_value=SimpleNamespace(to_dict=lambda: dict(row)))
    monkeypatch.setattr(routes, "compute_egsi_m_for_date", compute)
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as result:
        result.compute_mock = compute
        yield result


class TestEGSIMEndpoints:
    """Regression tests for EGSI-M API endpoints."""
    
    def test_egsi_m_status_endpoint(self, client):
        """Test /api/v1/indices/egsi-m/status returns valid response."""
        response = client.get('/api/v1/indices/egsi-m/status')
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'success' in data
        assert data['success'] is True
        assert 'enabled' in data
        assert 'model_version' in data
        assert data['model_version'] == 'egsi_m_v1'
    
    def test_egsi_m_public_endpoint(self, client):
        """Test /api/v1/indices/egsi-m/public returns valid response structure."""
        response = client.get('/api/v1/indices/egsi-m/public')
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'success' in data
        if data.get('data'):
            assert 'value' in data['data'] or 'value' in data
            assert 'band' in data['data'] or 'band' in data
    
    def test_egsi_m_latest_endpoint(self, client):
        """Test /api/v1/indices/egsi-m/latest returns valid response structure."""
        response = client.get('/api/v1/indices/egsi-m/latest')
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'success' in data
    
    def test_egsi_m_history_endpoint(self, client):
        """Test /api/v1/indices/egsi-m/history returns valid response structure."""
        response = client.get('/api/v1/indices/egsi-m/history?days=7')
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'success' in data
        assert 'data' in data
        assert isinstance(data['data'], list)
    
    def test_egsi_m_date_endpoint_valid_format(self, client):
        """Test /api/v1/indices/egsi-m/{date} with valid date format."""
        test_date = (date.today() - timedelta(days=1)).isoformat()
        response = client.get(f'/api/v1/indices/egsi-m/{test_date}')
        
        assert response.status_code in [200, 404]
        data = response.json()
        
        if response.status_code == 200:
            assert 'success' in data
        else:
            assert 'detail' in data
    
    def test_egsi_m_date_endpoint_invalid_format(self, client):
        """Test /api/v1/indices/egsi-m/{date} with invalid date format returns 400."""
        response = client.get('/api/v1/indices/egsi-m/invalid-date')
        
        assert response.status_code == 400
        data = response.json()
        assert 'detail' in data
    
    def test_egsi_m_status_not_shadowed_by_date_route(self, client):
        """
        Regression test: Ensure /status is not captured by /{date} route.
        
        This test ensures the route ordering is correct - static routes like
        /status must be defined before dynamic routes like /{date}.
        """
        response = client.get('/api/v1/indices/egsi-m/status')
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'enabled' in data
        assert 'model_version' in data
        
        assert 'Invalid date format' not in str(data)
    
    def test_egsi_m_compute_endpoint_requires_body(self, client):
        """Test /api/v1/indices/egsi-m/compute requires request body."""
        response = client.post('/api/v1/indices/egsi-m/compute')
        
        assert response.status_code == 422
        client.compute_mock.assert_not_called()
    
    def test_egsi_m_compute_endpoint_valid_request(self, client):
        """Test /api/v1/indices/egsi-m/compute with valid request body."""
        test_date = date.today().isoformat()
        response = client.post(
            '/api/v1/indices/egsi-m/compute',
            json={'date': test_date, 'force': False}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert 'success' in data
        assert data['success'] is True
        client.compute_mock.assert_called_once_with(date.fromisoformat(test_date), force=False)


class TestEGSIRiskBands:
    """Tests for EGSI-M risk band logic."""
    
    def test_status_returns_valid_band_in_latest(self, client):
        """If latest data exists, band should be one of the valid bands."""
        response = client.get('/api/v1/indices/egsi-m/status')
        
        assert response.status_code == 200
        data = response.json()
        
        if data.get('latest') and data['latest'].get('band'):
            valid_bands = ['LOW', 'NORMAL', 'ELEVATED', 'HIGH', 'CRITICAL']
            assert data['latest']['band'] in valid_bands


class TestEGSIFeatureFlag:
    """Tests for EGSI feature flag behavior."""
    
    def test_status_shows_enabled_state(self, client):
        """Status endpoint should show whether EGSI is enabled."""
        response = client.get('/api/v1/indices/egsi-m/status')
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'enabled' in data
        assert isinstance(data['enabled'], bool)


def run_tests():
    """Run all EGSI endpoint tests manually."""
    return pytest.main([__file__, "-q"]) == 0


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
