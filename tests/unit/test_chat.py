import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../chat"))

from fastapi.testclient import TestClient


class TestDetectLookback(unittest.TestCase):

    def setUp(self):
        import app
        self.ad = app

    def test_last_hour(self):
        self.assertEqual(self.ad.detect_lookback("what happened last hour?"), 3600)

    def test_last_3_hours(self):
        self.assertEqual(self.ad.detect_lookback("show me last 3 hours"), 10800)

    def test_last_30_minutes(self):
        self.assertEqual(self.ad.detect_lookback("last 30 min"), 1800)

    def test_yesterday(self):
        self.assertEqual(self.ad.detect_lookback("how was yesterday?"), 86400)

    def test_last_24h(self):
        self.assertEqual(self.ad.detect_lookback("last 24h trend"), 86400)

    def test_last_2_days(self):
        self.assertEqual(self.ad.detect_lookback("last 2 days"), 172800)

    def test_no_match(self):
        self.assertIsNone(self.ad.detect_lookback("is my server healthy?"))

    def test_is_cpu_normal(self):
        self.assertIsNone(self.ad.detect_lookback("Is my CPU usage normal?"))


class TestSummariseRange(unittest.TestCase):

    def setUp(self):
        import app
        self.ad = app

    def test_basic_summary(self):
        values = [{"time": i, "value": str(v)} for i, v in enumerate([10.0, 20.0, 30.0])]
        result = self.ad.summarise_range(values, "%")
        self.assertIn("min=10.0%", result)
        self.assertIn("avg=20.0%", result)
        self.assertIn("max=30.0%", result)

    def test_empty_returns_no_data(self):
        self.assertEqual(self.ad.summarise_range([]), "no data")

    def test_nan_values_ignored(self):
        values = [{"time": 0, "value": "NaN"}, {"time": 1, "value": "50.0"}]
        result = self.ad.summarise_range(values)
        self.assertIn("50.0", result)


class TestGetServers(unittest.TestCase):

    @patch("requests.get")
    def test_returns_sorted_instances(self, mock_get):
        mock_get.return_value = MagicMock(
            json=lambda: {
                "data": {
                    "result": [
                        {"metric": {"instance": "server-b:8000"}},
                        {"metric": {"instance": "server-a:8000"}},
                    ]
                }
            }
        )
        import app
        result = app.get_servers()
        self.assertEqual(result, ["server-a:8000", "server-b:8000"])

    @patch("requests.get", side_effect=Exception("network error"))
    def test_returns_empty_on_error(self, _mock):
        import app
        self.assertEqual(app.get_servers(), [])


class TestStatusEndpoint(unittest.TestCase):

    @patch("requests.get")
    def test_status_returns_metrics_key(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": {"result": [{"value": [0, "42.0"]}]}}
        )
        import app
        client = TestClient(app.app)
        resp = client.get("/status")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("metrics", resp.json())

    @patch("requests.get", side_effect=Exception("unreachable"))
    def test_status_handles_prometheus_down(self, _mock):
        import app
        client = TestClient(app.app)
        resp = client.get("/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("metrics", data)
        self.assertIn("N/A", data["metrics"])


class TestServersEndpoint(unittest.TestCase):

    @patch("requests.get")
    def test_servers_returns_list(self, mock_get):
        mock_get.return_value = MagicMock(
            json=lambda: {
                "data": {
                    "result": [{"metric": {"instance": "collector:8000"}}]
                }
            }
        )
        import app
        client = TestClient(app.app)
        resp = client.get("/servers")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("servers", resp.json())


class TestChatEndpoint(unittest.TestCase):

    @patch("requests.post")
    @patch("requests.get")
    def test_chat_returns_response(self, mock_get, mock_post):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": {"result": [{"value": [0, "30.0"]}]}}
        )
        mock_post.return_value = MagicMock(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"response": "Server looks healthy."}
        )
        import app
        client = TestClient(app.app)
        resp = client.post("/chat", json={"message": "is my server ok?"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("healthy", resp.text)

    @patch("requests.post", side_effect=__import__("requests").exceptions.ConnectionError)
    @patch("requests.get")
    def test_chat_handles_ollama_down(self, mock_get, _mock_post):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": {"result": []}}
        )
        import app
        client = TestClient(app.app)
        resp = client.post("/chat", json={"message": "hello"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Ollama", resp.text)

    @patch("requests.post")
    @patch("requests.get")
    def test_chat_with_server_filter(self, mock_get, mock_post):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": {"result": [{"value": [0, "55.0"]}]}}
        )
        mock_post.return_value = MagicMock(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"response": "Server-A is fine."}
        )
        import app
        client = TestClient(app.app)
        resp = client.post("/chat", json={"message": "status?", "server": "server-a:8000"})
        self.assertEqual(resp.status_code, 200)

    @patch("requests.post")
    @patch("requests.get")
    def test_chat_historical_query_includes_history(self, mock_get, mock_post):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "data": {
                    "result": [{"values": [[i, "40.0"] for i in range(60)]}]
                }
            }
        )
        mock_post.return_value = MagicMock(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"response": "CPU was stable last hour."}
        )
        import app

        captured_system = []
        original_post = mock_post.side_effect

        def capture(url, json=None, **kw):
            if json and "system" in json:
                captured_system.append(json["system"])
            return MagicMock(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {"response": "CPU was stable."}
            )

        mock_post.side_effect = capture
        client = TestClient(app.app)
        client.post("/chat", json={"message": "what happened last hour?"})
        self.assertTrue(len(captured_system) > 0)
        self.assertIn("HISTORICAL", captured_system[0])


if __name__ == "__main__":
    unittest.main()
