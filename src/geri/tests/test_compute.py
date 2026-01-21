"""
Unit tests for GERI v1 compute functions.
"""
import unittest
from datetime import datetime

from src.geri.types import (
    AlertRecord,
    RiskBand,
    get_band,
    GERIComponents,
    HistoricalBaseline,
)
from src.geri.compute import (
    severity_from_risk_score,
    risk_score_from_severity,
    get_effective_severity,
    get_effective_risk_score,
    compute_components,
)
from src.geri.normalize import (
    normalize_value,
    normalize_components,
    calculate_geri_value,
    calculate_trends,
)


class TestBandMapping(unittest.TestCase):
    """Test risk band mapping."""
    
    def test_low_band(self):
        self.assertEqual(get_band(0), RiskBand.LOW)
        self.assertEqual(get_band(25), RiskBand.LOW)
    
    def test_moderate_band(self):
        self.assertEqual(get_band(26), RiskBand.MODERATE)
        self.assertEqual(get_band(50), RiskBand.MODERATE)
    
    def test_elevated_band(self):
        self.assertEqual(get_band(51), RiskBand.ELEVATED)
        self.assertEqual(get_band(75), RiskBand.ELEVATED)
    
    def test_critical_band(self):
        self.assertEqual(get_band(76), RiskBand.CRITICAL)
        self.assertEqual(get_band(100), RiskBand.CRITICAL)


class TestSeverityMapping(unittest.TestCase):
    """Test severity <-> risk_score conversions."""
    
    def test_severity_from_risk_score(self):
        self.assertEqual(severity_from_risk_score(90), 5)
        self.assertEqual(severity_from_risk_score(70), 4)
        self.assertEqual(severity_from_risk_score(50), 3)
        self.assertEqual(severity_from_risk_score(25), 2)
        self.assertEqual(severity_from_risk_score(10), 1)
    
    def test_severity_from_risk_score_none(self):
        self.assertEqual(severity_from_risk_score(None), 3)
    
    def test_risk_score_from_severity(self):
        self.assertEqual(risk_score_from_severity(5), 90.0)
        self.assertEqual(risk_score_from_severity(4), 70.0)
        self.assertEqual(risk_score_from_severity(3), 50.0)
        self.assertEqual(risk_score_from_severity(2), 30.0)
        self.assertEqual(risk_score_from_severity(1), 10.0)
    
    def test_risk_score_from_severity_none(self):
        self.assertEqual(risk_score_from_severity(None), 50.0)


class TestNormalization(unittest.TestCase):
    """Test normalization functions."""
    
    def test_normalize_basic(self):
        self.assertEqual(normalize_value(50, 0, 100), 50.0)
        self.assertEqual(normalize_value(0, 0, 100), 0.0)
        self.assertEqual(normalize_value(100, 0, 100), 100.0)
    
    def test_normalize_clamp(self):
        self.assertEqual(normalize_value(150, 0, 100), 100.0)
        self.assertEqual(normalize_value(-50, 0, 100), 0.0)
    
    def test_normalize_same_min_max_zero(self):
        self.assertEqual(normalize_value(0, 0, 0), 0.0)
    
    def test_normalize_same_min_max_nonzero(self):
        self.assertEqual(normalize_value(50, 50, 50), 50.0)
    
    def test_normalize_range(self):
        self.assertEqual(normalize_value(25, 0, 50), 50.0)
        self.assertEqual(normalize_value(75, 50, 100), 50.0)


class TestTrends(unittest.TestCase):
    """Test trend calculations."""
    
    def test_trends_no_history(self):
        trend_1d, trend_7d = calculate_trends(50, [])
        self.assertIsNone(trend_1d)
        self.assertIsNone(trend_7d)
    
    def test_trend_1d(self):
        trend_1d, trend_7d = calculate_trends(50, [40])
        self.assertEqual(trend_1d, 10)
        self.assertIsNone(trend_7d)
    
    def test_trend_7d(self):
        trend_1d, trend_7d = calculate_trends(50, [40, 45, 50, 55, 45, 50, 45])
        self.assertEqual(trend_1d, 10)
        self.assertEqual(trend_7d, 3)
    
    def test_trend_negative(self):
        trend_1d, trend_7d = calculate_trends(30, [50])
        self.assertEqual(trend_1d, -20)


class TestComputeComponents(unittest.TestCase):
    """Test component computation."""
    
    def test_empty_alerts(self):
        components = compute_components([])
        self.assertEqual(components.total_alerts, 0)
        self.assertEqual(components.high_impact_events, 0)
        self.assertEqual(components.regional_spikes, 0)
        self.assertEqual(components.asset_spikes, 0)
    
    def test_high_impact_count(self):
        alerts = [
            AlertRecord(
                id=1, alert_type='HIGH_IMPACT_EVENT', severity=5,
                risk_score=None, region='Europe', weight=1.0,
                created_at=datetime.now()
            ),
            AlertRecord(
                id=2, alert_type='HIGH_IMPACT_EVENT', severity=4,
                risk_score=None, region='Europe', weight=1.0,
                created_at=datetime.now()
            ),
        ]
        components = compute_components(alerts)
        self.assertEqual(components.high_impact_events, 2)
        self.assertEqual(components.high_impact_score, 9.0)
    
    def test_region_concentration(self):
        alerts = [
            AlertRecord(
                id=1, alert_type='HIGH_IMPACT_EVENT', severity=5,
                risk_score=80, region='Europe', weight=1.0,
                created_at=datetime.now()
            ),
            AlertRecord(
                id=2, alert_type='REGIONAL_RISK_SPIKE', severity=4,
                risk_score=60, region='Europe', weight=1.0,
                created_at=datetime.now()
            ),
            AlertRecord(
                id=3, alert_type='ASSET_RISK_ALERT', severity=3,
                risk_score=20, region='Asia', weight=1.0,
                created_at=datetime.now()
            ),
        ]
        components = compute_components(alerts)
        self.assertEqual(components.regions_count, 2)
        self.assertEqual(len(components.top_regions), 2)
        self.assertEqual(components.top_regions[0]['region'], 'Europe')


class TestGERIFormula(unittest.TestCase):
    """Test GERI weighted formula."""
    
    def test_geri_all_zero(self):
        components = GERIComponents()
        value = calculate_geri_value(components)
        self.assertEqual(value, 0)
    
    def test_geri_all_max(self):
        components = GERIComponents(
            norm_high_impact=100,
            norm_regional_spike=100,
            norm_asset_risk=100,
            norm_region_concentration=100,
        )
        value = calculate_geri_value(components)
        self.assertEqual(value, 100)
    
    def test_geri_weighted(self):
        components = GERIComponents(
            norm_high_impact=50,
            norm_regional_spike=50,
            norm_asset_risk=50,
            norm_region_concentration=50,
        )
        value = calculate_geri_value(components)
        self.assertEqual(value, 50)
    
    def test_geri_weights_correct(self):
        components = GERIComponents(
            norm_high_impact=100,
            norm_regional_spike=0,
            norm_asset_risk=0,
            norm_region_concentration=0,
        )
        value = calculate_geri_value(components)
        self.assertEqual(value, 40)


if __name__ == '__main__':
    unittest.main()
