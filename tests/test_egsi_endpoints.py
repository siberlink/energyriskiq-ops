"""
EGSI Endpoint Regression Tests

Tests for EGSI-M API endpoints to ensure route stability and correct responses.
"""
import pytest
import requests
import os
from datetime import date, timedelta

BASE_URL = os.environ.get('TEST_BASE_URL', 'http://localhost:5000')


class TestEGSIMEndpoints:
    """Regression tests for EGSI-M API endpoints."""
    
    def test_egsi_m_status_endpoint(self):
        """Test /api/v1/indices/egsi-m/status returns valid response."""
        response = requests.get(f'{BASE_URL}/api/v1/indices/egsi-m/status')
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'success' in data
        assert data['success'] is True
        assert 'enabled' in data
        assert 'model_version' in data
        assert data['model_version'] == 'egsi_m_v1'
    
    def test_egsi_m_public_endpoint(self):
        """Test /api/v1/indices/egsi-m/public returns valid response structure."""
        response = requests.get(f'{BASE_URL}/api/v1/indices/egsi-m/public')
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'success' in data
        if data.get('data'):
            assert 'value' in data['data'] or 'value' in data
            assert 'band' in data['data'] or 'band' in data
    
    def test_egsi_m_latest_endpoint(self):
        """Test /api/v1/indices/egsi-m/latest returns valid response structure."""
        response = requests.get(f'{BASE_URL}/api/v1/indices/egsi-m/latest')
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'success' in data
    
    def test_egsi_m_history_endpoint(self):
        """Test /api/v1/indices/egsi-m/history returns valid response structure."""
        response = requests.get(f'{BASE_URL}/api/v1/indices/egsi-m/history?days=7')
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'success' in data
        assert 'data' in data
        assert isinstance(data['data'], list)
    
    def test_egsi_m_date_endpoint_valid_format(self):
        """Test /api/v1/indices/egsi-m/{date} with valid date format."""
        test_date = (date.today() - timedelta(days=1)).isoformat()
        response = requests.get(f'{BASE_URL}/api/v1/indices/egsi-m/{test_date}')
        
        assert response.status_code in [200, 404]
        data = response.json()
        
        if response.status_code == 200:
            assert 'success' in data
        else:
            assert 'detail' in data
    
    def test_egsi_m_date_endpoint_invalid_format(self):
        """Test /api/v1/indices/egsi-m/{date} with invalid date format returns 400."""
        response = requests.get(f'{BASE_URL}/api/v1/indices/egsi-m/invalid-date')
        
        assert response.status_code == 400
        data = response.json()
        assert 'detail' in data
    
    def test_egsi_m_status_not_shadowed_by_date_route(self):
        """
        Regression test: Ensure /status is not captured by /{date} route.
        
        This test ensures the route ordering is correct - static routes like
        /status must be defined before dynamic routes like /{date}.
        """
        response = requests.get(f'{BASE_URL}/api/v1/indices/egsi-m/status')
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'enabled' in data
        assert 'model_version' in data
        
        assert 'Invalid date format' not in str(data)
    
    def test_egsi_m_compute_endpoint_requires_body(self):
        """Test /api/v1/indices/egsi-m/compute requires request body."""
        response = requests.post(f'{BASE_URL}/api/v1/indices/egsi-m/compute')
        
        assert response.status_code == 422
    
    def test_egsi_m_compute_endpoint_valid_request(self):
        """Test /api/v1/indices/egsi-m/compute with valid request body."""
        test_date = date.today().isoformat()
        response = requests.post(
            f'{BASE_URL}/api/v1/indices/egsi-m/compute',
            json={'date': test_date, 'force': False}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert 'success' in data


class TestEGSIRiskBands:
    """Tests for EGSI-M risk band logic."""
    
    def test_status_returns_valid_band_in_latest(self):
        """If latest data exists, band should be one of the valid bands."""
        response = requests.get(f'{BASE_URL}/api/v1/indices/egsi-m/status')
        
        assert response.status_code == 200
        data = response.json()
        
        if data.get('latest') and data['latest'].get('band'):
            valid_bands = ['LOW', 'NORMAL', 'ELEVATED', 'HIGH', 'CRITICAL']
            assert data['latest']['band'] in valid_bands


class TestEGSIFeatureFlag:
    """Tests for EGSI feature flag behavior."""
    
    def test_status_shows_enabled_state(self):
        """Status endpoint should show whether EGSI is enabled."""
        response = requests.get(f'{BASE_URL}/api/v1/indices/egsi-m/status')
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'enabled' in data
        assert isinstance(data['enabled'], bool)


def run_tests():
    """Run all EGSI endpoint tests manually."""
    import sys
    
    tests = TestEGSIMEndpoints()
    test_methods = [m for m in dir(tests) if m.startswith('test_')]
    
    passed = 0
    failed = 0
    
    for method_name in test_methods:
        try:
            method = getattr(tests, method_name)
            method()
            print(f"PASS: {method_name}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {method_name} - {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {method_name} - {e}")
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
