import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../ml"))


def _make_df(n: int, values=None, slope: float = 0.0) -> pd.DataFrame:
    """Build a fake Prometheus DataFrame with n rows."""
    timestamps = pd.date_range("2024-01-01", periods=n, freq="15s")
    if values is None:
        vals = np.full(n, 50.0) + slope * np.arange(n)
    else:
        vals = np.array(values, dtype=float)
    return pd.DataFrame({"timestamp": timestamps, "value": vals})


class TestGetInstances(unittest.TestCase):

    @patch("requests.get")
    def test_returns_instance_list(self, mock_get):
        mock_get.return_value = MagicMock(
            json=lambda: {
                "data": {
                    "result": [
                        {"metric": {"instance": "collector:8000"}},
                        {"metric": {"instance": "192.168.1.10:8000"}},
                    ]
                }
            }
        )
        import anomaly_detector as ad
        instances = ad.get_instances()
        self.assertEqual(instances, ["collector:8000", "192.168.1.10:8000"])

    @patch("requests.get", side_effect=Exception("network error"))
    def test_returns_empty_on_error(self, _mock):
        import anomaly_detector as ad
        self.assertEqual(ad.get_instances(), [])


class TestIsolationForest(unittest.TestCase):

    @patch("anomaly_detector.query_range")
    def test_normal_data_sets_no_anomaly(self, mock_query):
        # All metrics flat → no anomaly
        flat = _make_df(60, slope=0.0)
        mock_query.side_effect = lambda metric, instance, **kw: flat.copy()
        import anomaly_detector as ad
        with patch.object(ad.anomaly_detected.labels(instance="test"), "set") as mock_set:
            ad.run_isolation_forest("test")
            mock_set.assert_called_once_with(0)

    @patch("anomaly_detector.query_range")
    def test_skips_with_insufficient_data(self, mock_query):
        mock_query.side_effect = lambda metric, instance, **kw: _make_df(5)
        import anomaly_detector as ad
        with patch.object(ad.anomaly_score, "labels") as mock_labels:
            ad.run_isolation_forest("test")
            mock_labels.assert_not_called()

    @patch("anomaly_detector.query_range")
    def test_skips_when_empty(self, mock_query):
        mock_query.side_effect = lambda metric, instance, **kw: pd.DataFrame()
        import anomaly_detector as ad
        with patch.object(ad.anomaly_score, "labels") as mock_labels:
            ad.run_isolation_forest("test")
            mock_labels.assert_not_called()


class TestDiskForecast(unittest.TestCase):

    @patch("anomaly_detector.query_range")
    def test_growing_disk_returns_positive_days(self, mock_query):
        # Disk growing slowly: ~0.001% per second → will take a long time
        mock_query.return_value = _make_df(500, slope=0.001)
        import anomaly_detector as ad
        days_set = []
        real_labels = ad.disk_full_days.labels

        def capture_labels(**kwargs):
            gauge = real_labels(**kwargs)
            original_set = gauge.set
            def intercepted_set(v):
                days_set.append(v)
                original_set(v)
            gauge.set = intercepted_set
            return gauge

        with patch.object(ad.disk_full_days, "labels", side_effect=capture_labels):
            ad.run_disk_forecast("test")

        self.assertTrue(len(days_set) > 0)
        self.assertGreater(days_set[0], 0)

    @patch("anomaly_detector.query_range")
    def test_flat_disk_returns_minus_one(self, mock_query):
        mock_query.return_value = _make_df(500, slope=0.0)
        import anomaly_detector as ad
        days_set = []
        real_labels = ad.disk_full_days.labels

        def capture_labels(**kwargs):
            gauge = real_labels(**kwargs)
            original_set = gauge.set
            def intercepted_set(v):
                days_set.append(v)
                original_set(v)
            gauge.set = intercepted_set
            return gauge

        with patch.object(ad.disk_full_days, "labels", side_effect=capture_labels):
            ad.run_disk_forecast("test")

        self.assertEqual(days_set[0], -1)

    @patch("anomaly_detector.query_range")
    def test_insufficient_data_returns_minus_one(self, mock_query):
        mock_query.return_value = _make_df(10)
        import anomaly_detector as ad
        days_set = []
        real_labels = ad.disk_full_days.labels

        def capture_labels(**kwargs):
            gauge = real_labels(**kwargs)
            original_set = gauge.set
            def intercepted_set(v):
                days_set.append(v)
                original_set(v)
            gauge.set = intercepted_set
            return gauge

        with patch.object(ad.disk_full_days, "labels", side_effect=capture_labels):
            ad.run_disk_forecast("test")

        self.assertEqual(days_set[0], -1)


if __name__ == "__main__":
    unittest.main()
