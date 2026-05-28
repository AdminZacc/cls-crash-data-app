import unittest
from unittest.mock import patch

from crash_parser import (
    build_query_params,
    fetch_crash_geojson,
)
from crash_ui import build_dashboard_data


class CrashParserTests(unittest.TestCase):
    def test_build_query_params(self) -> None:
        params = build_query_params(
            longitude=-76.1775,
            latitude=36.7806,
            start_date="2020-01-01",
            end_date="2020-12-31",
        )

        self.assertEqual(
            params["where"],
            "CRASH_DT >= DATE '2020-01-01' AND CRASH_DT < DATE '2021-01-01'",
        )
        self.assertEqual(params["geometryType"], "esriGeometryPoint")
        self.assertEqual(params["spatialRel"], "esriSpatialRelIntersects")
        self.assertEqual(params["distance"], 5280.0)
        self.assertEqual(params["units"], "esriSRUnit_Foot")
        self.assertEqual(params["outFields"], "*")
        self.assertEqual(params["f"], "geojson")

    @patch("crash_parser.requests.get")
    def test_fetch_crash_geojson(self, mock_get) -> None:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "type": "FeatureCollection",
            "features": [{"type": "Feature"}, {"type": "Feature"}],
        }

        result = fetch_crash_geojson(
            "https://example.com/query",
            longitude=-76.1775,
            latitude=36.7806,
            end_date="2020-12-31",
        )

        self.assertEqual(result["feature_count"], 2)
        self.assertEqual(result["geojson"]["type"], "FeatureCollection")
        self.assertEqual(result["end_date"], "2020-12-31")
        mock_get.assert_called_once()

    @patch("crash_parser.requests.get")
    @patch("crash_parser.time.sleep")
    def test_fetch_crash_geojson_retries_on_429(self, mock_sleep, mock_get) -> None:
        first_response = unittest.mock.Mock()
        first_response.status_code = 429
        first_response.headers = {"Retry-After": "1"}
        second_response = unittest.mock.Mock()
        second_response.status_code = 200
        second_response.headers = {}
        second_response.json.return_value = {
            "type": "FeatureCollection",
            "features": [{"type": "Feature"}],
        }
        mock_get.side_effect = [first_response, second_response]

        result = fetch_crash_geojson("https://example.com/query", max_attempts=2)

        self.assertEqual(result["feature_count"], 1)
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once_with(1.0)

    def test_build_dashboard_data(self) -> None:
        summary = {
            "start_date": "2020-01-01",
            "end_date": None,
            "geojson": {
                "features": [
                    {
                        "properties": {
                            "CRASH_DT": 1756267200000,
                            "CRASH_SEVERITY": "C",
                            "PERSONS_INJURED": 2,
                            "K_PEOPLE": 0,
                            "VEH_COUNT": 2,
                            "ROUTE_OR_STREET_NM": "ROUTE A",
                            "PHYSICAL_JURIS": "134",
                            "DOCUMENT_NBR": 1,
                        }
                    },
                    {
                        "properties": {
                            "CRASH_DT": 1579410000000,
                            "CRASH_SEVERITY": "B",
                            "PERSONS_INJURED": 1,
                            "K_PEOPLE": 0,
                            "VEH_COUNT": 3,
                            "ROUTE_OR_STREET_NM": "ROUTE A",
                            "PHYSICAL_JURIS": "134",
                            "DOCUMENT_NBR": 2,
                        }
                    },
                ]
            },
        }

        dashboard = build_dashboard_data(summary)

        self.assertEqual(dashboard["records"], 2)
        self.assertEqual(dashboard["total_injured"], 3)
        self.assertEqual(dashboard["total_killed"], 0)
        self.assertEqual(dashboard["severity_counts"], {"B": 1, "C": 1})
        self.assertEqual(dashboard["top_route"], {"name": "ROUTE A", "count": 2})
        self.assertEqual(len(dashboard["recent_rows"]), 2)

    @patch("crash_parser.requests.get")
    @patch("crash_parser.time.sleep")
    def test_fetch_crash_geojson_raises_after_retries(self, mock_sleep, mock_get) -> None:
        response = unittest.mock.Mock()
        response.status_code = 500
        response.headers = {}
        mock_get.return_value = response

        with self.assertRaises(RuntimeError):
            fetch_crash_geojson("https://example.com/query", max_attempts=2)

        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)


if __name__ == "__main__":
    unittest.main()
