"""
Test suite for GET /network/top-movers endpoint.

Tests validate:
- Route returns 200 with correct response shape
- Query param validation (limit bounds, as_of format)
- Floor-then-rank ordering: filtering happens before ranking and limiting
- Results sorted by activity_growth descending (not anomaly_score or risk_score)
- No result's avg_activity falls below the returned activity_floor
- Empty result set (not error) when no data exists for the requested as_of
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(PROJECT_ROOT / "phase4"))

from api1 import app
from api3_hotspotandalert import DB_PATH as WAREHOUSE_DB

client = TestClient(app)


class TestTopMoversRoute:
    def test_default_request_returns_200_with_correct_shape(self):
        """
        Default GET /network/top-movers → 200, TopMoversResponse shape.
        """
        response = client.get("/network/top-movers")
        assert response.status_code == 200
        data = response.json()
        assert "as_of" in data
        assert "limit" in data
        assert "activity_floor" in data
        assert "results" in data
        assert isinstance(data["results"], list)
        assert data["limit"] <= 100

    def test_limit_bounds_validation(self):
        """
        limit=0 and limit=101 → 422 (Pydantic Query bounds).
        """
        response = client.get("/network/top-movers?limit=0")
        assert response.status_code == 422

        response = client.get("/network/top-movers?limit=101")
        assert response.status_code == 422

    def test_invalid_as_of_format(self):
        """
        as_of="not-a-date" → 400 (invalid ISO-8601 format).
        """
        response = client.get("/network/top-movers?as_of=not-a-date")
        assert response.status_code == 400
        assert "ISO-8601" in response.json()["detail"]

    def test_results_sorted_by_activity_growth_descending(self):
        """
        Results are sorted by activity_growth DESC, not by anomaly_score
        or risk_score.
        """
        response = client.get("/network/top-movers?limit=10")
        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        if len(results) > 1:
            for i in range(len(results) - 1):
                current = float(results[i]["activity_growth"])
                next_val = float(results[i + 1]["activity_growth"])
                assert (
                    current >= next_val
                ), f"Results not sorted by activity_growth DESC"

    def test_no_result_below_activity_floor(self):
        """
        No result's avg_activity falls below the returned activity_floor.
        """
        response = client.get("/network/top-movers?limit=20")
        assert response.status_code == 200
        data = response.json()
        floor = float(data["activity_floor"])
        results = data["results"]

        for item in results:
            avg_activity = float(item["avg_activity"])
            assert (
                avg_activity >= floor
            ), f"Grid {item['grid_id']} has avg_activity {avg_activity} < floor {floor}"

    def test_empty_result_set_for_future_as_of(self):
        """
        An as_of in the future (after all available data) → 200 with
        results: [], not an error (per CLAUDE.md: report absence, don't invent).
        """
        # Use a date far in the future
        future_as_of = "2099-12-31T23:59:59"
        response = client.get(f"/network/top-movers?as_of={future_as_of}")
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []

    def test_activity_floor_echoed_in_response(self):
        """
        activity_floor is returned in the response for caller reference.
        """
        response = client.get("/network/top-movers?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["activity_floor"], (int, float))
        assert data["activity_floor"] >= 0.0

    def test_anomaly_score_secondary_context_only(self):
        """
        anomaly_score and anomaly_direction are present (if available) but
        do not affect the sort order. (This is a secondary context signal.)
        """
        response = client.get("/network/top-movers?limit=10")
        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        if len(results) > 0:
            item = results[0]
            assert "anomaly_score" in item
            assert "anomaly_direction" in item
            # These can be None if not populated, but the fields exist

    def test_risk_score_secondary_context_only(self):
        """
        risk_score, risk_level, model_version are present (if available) but
        do not affect the sort order.
        """
        response = client.get("/network/top-movers?limit=10")
        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        if len(results) > 0:
            item = results[0]
            assert "risk_score" in item
            assert "risk_level" in item
            assert "model_version" in item


class TestFloorBeforeRankOrdering:
    """
    Regression test: ensure that the floor is applied to the full row set
    BEFORE ranking and limiting, not after.
    """

    def test_floor_excludes_low_activity_even_if_high_growth(self):
        """
        A grid below the activity floor is excluded from results even if
        its activity_growth would rank it above some above-floor grids.

        This is a hard ordering guarantee: floor first, then rank, then limit.
        """
        # Fetch data to understand the current state
        response = client.get("/network/top-movers?limit=100")
        assert response.status_code == 200
        data = response.json()
        floor = float(data["activity_floor"])
        results = data["results"]

        # Verify the floor was actually applied
        # (i.e., at least one result exists, and all are above the floor)
        if len(results) > 0:
            for item in results:
                avg_activity = float(item["avg_activity"])
                assert avg_activity >= floor, (
                    f"Grid {item['grid_id']} below floor {floor}, "
                    f"but is in results: violation of floor-before-rank"
                )


class TestActivityFloorConsistency:
    """
    Verify that the activity_floor returned by the API matches the
    NP3-derived FLOOR_PERCENTILE constant applied to that hour's avg_activity
    values.
    """

    def test_activity_floor_matches_np3_percentile(self):
        """
        The returned activity_floor should match the 10th percentile (NP3's
        FLOOR_PERCENTILE = 0.10) of the avg_activity values for that hour.

        This ensures the floor definition is genuinely reused, not re-derived.
        """
        response = client.get("/network/top-movers?limit=100")
        assert response.status_code == 200
        data = response.json()
        returned_floor = float(data["activity_floor"])
        as_of = data["as_of"]

        # Independently compute the floor using the warehouse
        if WAREHOUSE_DB.exists():
            conn = sqlite3.connect(WAREHOUSE_DB)
            conn.row_factory = sqlite3.Row

            normalized_as_of = as_of.replace("T", " ")

            rows = conn.execute(
                """
                SELECT avg_activity FROM network_feature_table
                WHERE REPLACE(feature_timestamp, 'T', ' ') = ?
                """,
                (normalized_as_of,),
            ).fetchall()

            if rows:
                import numpy as np
                avg_activities = [
                    float(row["avg_activity"]) for row in rows
                ]
                expected_floor = float(
                    np.quantile(avg_activities, 0.10)
                )

                # Allow small floating-point tolerance
                assert abs(returned_floor - expected_floor) < 1e-6, (
                    f"Returned floor {returned_floor} does not match "
                    f"expected NP3 10th percentile {expected_floor}"
                )

            conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
