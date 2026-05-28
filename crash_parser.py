import json
import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import requests

DEFAULT_LONGITUDE = -76.1775
DEFAULT_LATITUDE = 36.7806
DEFAULT_DISTANCE_MILES = 1.0
DEFAULT_WHERE = "CRASH_DT >= DATE '2020-01-01'"
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BACKOFF_SECONDS = 1.0
FEET_PER_MILE = 5280.0


def build_query_params(
    longitude: float,
    latitude: float,
    start_date: str,
    end_date: Optional[str] = None,
    distance_miles: float = DEFAULT_DISTANCE_MILES,
    where_clause: Optional[str] = None,
) -> dict[str, Any]:
    if where_clause:
        where_value = where_clause
    elif end_date:
        end_date_value = datetime.strptime(end_date, "%Y-%m-%d").date() + timedelta(days=1)
        where_value = (
            f"CRASH_DT >= DATE '{start_date}' AND CRASH_DT < DATE '{end_date_value.isoformat()}'"
        )
    else:
        where_value = f"CRASH_DT >= DATE '{start_date}'"

    return {
        "where": where_value,
        "geometry": json.dumps({"x": longitude, "y": latitude}),
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": distance_miles * FEET_PER_MILE,
        "units": "esriSRUnit_Foot",
        "outFields": "*",
        "f": "geojson",
    }


def fetch_crash_geojson(
    api_url: str,
    longitude: float = DEFAULT_LONGITUDE,
    latitude: float = DEFAULT_LATITUDE,
    start_date: str = "2020-01-01",
    end_date: Optional[str] = None,
    distance_miles: float = DEFAULT_DISTANCE_MILES,
    where_clause: Optional[str] = None,
    timeout: float = 30.0,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
) -> dict[str, Any]:
    params = build_query_params(
        longitude=longitude,
        latitude=latitude,
        start_date=start_date,
        end_date=end_date,
        distance_miles=distance_miles,
        where_clause=where_clause,
    )

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")

    last_error: Optional[Exception] = None
    delay = backoff_seconds

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(api_url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            last_error = exc
        else:
            if response.status_code == 200:
                crash_geojson = response.json()
                if not isinstance(crash_geojson, dict):
                    raise ValueError("Unexpected response format: expected a GeoJSON object.")

                error_payload = crash_geojson.get("error")
                if isinstance(error_payload, dict):
                    error_message = error_payload.get("message") or "ArcGIS returned an error response."
                    error_details = error_payload.get("details")
                    if isinstance(error_details, list) and error_details:
                        error_message = f"{error_message} {'; '.join(str(item) for item in error_details)}"
                    raise RuntimeError(error_message)

                features = crash_geojson.get("features")
                if not isinstance(features, list):
                    raise ValueError(
                        "Unexpected response format: missing GeoJSON features. "
                        f"Response keys: {', '.join(sorted(crash_geojson.keys()))}"
                    )

                return {
                    "api_url": api_url,
                    "longitude": longitude,
                    "latitude": latitude,
                    "start_date": start_date,
                    "end_date": end_date,
                    "distance_miles": distance_miles,
                    "where": params["where"],
                    "feature_count": len(features),
                    "query_params": params,
                    "geojson": crash_geojson,
                }

            status_code = response.status_code
            retry_after = response.headers.get("Retry-After")
            retryable = status_code == 429 or 500 <= status_code < 600
            if not retryable:
                raise RuntimeError(f"Failed to fetch data: {status_code}")

            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    pass

            last_error = RuntimeError(f"Failed to fetch data: {status_code}")

        if attempt < max_attempts:
            time.sleep(delay)
            delay *= 2

    if last_error is not None:
        raise RuntimeError(str(last_error))

    raise RuntimeError("Failed to fetch data for an unknown reason.")


def print_summary(summary: dict[str, Any]) -> None:
    print("=== Crash Query Result ===")
    print(f"Endpoint: {summary['api_url']}")
    print(f"Location: ({summary['latitude']}, {summary['longitude']})")
    print(f"Distance: {summary['distance_miles']} mile(s)")
    print(f"Start date: {summary['start_date']}")
    if summary.get("end_date"):
        print(f"End date: {summary['end_date']}")
    print(f"Where: {summary['where']}")
    print(f"Successfully retrieved {summary['feature_count']} crash records.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Query a crash feature layer and print a summary.")
    parser.add_argument("api_url", type=str, help="Crash feature layer /query endpoint URL")
    parser.add_argument(
        "--longitude",
        type=float,
        default=DEFAULT_LONGITUDE,
        help=f"Longitude for the point query (default: {DEFAULT_LONGITUDE})",
    )
    parser.add_argument(
        "--latitude",
        type=float,
        default=DEFAULT_LATITUDE,
        help=f"Latitude for the point query (default: {DEFAULT_LATITUDE})",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2020-01-01",
        help="Inclusive lower bound for CRASH_DT (default: 2020-01-01)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Optional inclusive upper bound date for CRASH_DT (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--distance",
        type=float,
        default=DEFAULT_DISTANCE_MILES,
        help=f"Distance in miles around the query point (default: {DEFAULT_DISTANCE_MILES})",
    )
    parser.add_argument(
        "--where",
        type=str,
        default=None,
        help=f"Optional custom WHERE clause (default: {DEFAULT_WHERE})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write the GeoJSON response",
    )

    args = parser.parse_args()

    try:
        summary = fetch_crash_geojson(
            args.api_url,
            longitude=args.longitude,
            latitude=args.latitude,
            start_date=args.start_date,
            end_date=args.end_date,
            distance_miles=args.distance,
            where_clause=args.where,
            timeout=args.timeout,
        )
    except Exception as exc:
        raise SystemExit(str(exc))

    print_summary(summary)

    if args.json_out is not None:
        args.json_out.write_text(json.dumps(summary["geojson"], indent=2), encoding="utf-8")
        print(f"\nGeoJSON written to: {args.json_out}")


if __name__ == "__main__":
    main()
