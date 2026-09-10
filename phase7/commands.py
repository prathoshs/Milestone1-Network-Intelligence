"""
Phase 7 Project Slash Commands

These helpers implement common diagnostic and review operations:
  /check-pipeline    - Pipeline health and staleness check
  /explain-grid      - Grid activity + severity analysis
  /review-anomaly    - Compare rule/ML/anomaly signals
  /test-api          - Run API test suite
  /network-health    - Validate grain integrity

Usage: Import and call the appropriate function, or invoke via wrapper scripts.
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

# Project paths
WAREHOUSE_PATH = Path(__file__).parent.parent / "phase3/warehouse_output/network_analytics.db"
GEOJSON_PATH = Path(__file__).parent.parent / "phase3/milano-grid.geojson"


def check_pipeline(as_of: Optional[str] = None) -> dict:
    """
    GET /pipeline/status equivalent: Check pipeline health, staleness, rejected rows.

    Returns:
    {
        "status": "healthy|warning|failure",
        "last_run": "ISO-8601 timestamp",
        "max_available_timestamp": "ISO-8601",
        "staleness_hours": float,
        "warehouse_rows": int,
        "rejected_rows": int,
        "rejected_reasons": [...],
        "components": [{"name": str, "status": str}]
    }
    """
    try:
        conn = sqlite3.connect(WAREHOUSE_PATH)
        cursor = conn.cursor()

        # Get max timestamp in fact table
        cursor.execute("SELECT MAX(timestamp) FROM fact_network_activity")
        max_ts = cursor.fetchone()[0]

        # Get row counts
        cursor.execute("SELECT COUNT(*) FROM fact_network_activity")
        warehouse_rows = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM rejected_records WHERE reason IS NOT NULL")
        rejected_rows = cursor.fetchone()[0]

        cursor.execute("SELECT DISTINCT reason FROM rejected_records WHERE reason IS NOT NULL")
        rejected_reasons = [r[0] for r in cursor.fetchall()]

        conn.close()

        # Calculate staleness
        if max_ts:
            last_run = datetime.fromisoformat(max_ts)
            staleness = (datetime.now() - last_run).total_seconds() / 3600
            status = "healthy" if staleness < 24 else "warning" if staleness < 72 else "failure"
        else:
            last_run = None
            staleness = None
            status = "failure"

        return {
            "status": status,
            "last_run": str(max_ts) if max_ts else None,
            "max_available_timestamp": str(max_ts) if max_ts else None,
            "staleness_hours": staleness,
            "warehouse_rows": warehouse_rows,
            "rejected_rows": rejected_rows,
            "rejected_reasons": rejected_reasons,
            "components": [
                {"name": "warehouse", "status": "operational" if warehouse_rows > 0 else "no_data"},
                {"name": "data_quality", "status": "good" if rejected_rows == 0 else "issues"},
            ]
        }
    except Exception as e:
        return {"status": "failure", "error": str(e)}


def explain_grid(grid_id: int, as_of: Optional[str] = None) -> dict:
    """
    Given grid_id, gather activity, features, anomaly score, location.
    Produce SEVERITY / EVIDENCE / INTERPRETATION / NEXT CHECKS response.

    Returns:
    {
        "grid_id": int,
        "severity": "high|medium|low",
        "severity_reason": str,
        "evidence": {
            "activity_level": float,
            "baseline_activity": float,
            "ml_risk_score": float,
            "anomaly_score": float,
            "location": {"lat": float, "lng": float, "description": str}
        },
        "interpretation": str,
        "next_checks": [str, ...]
    }
    """
    try:
        conn = sqlite3.connect(WAREHOUSE_PATH)
        cursor = conn.cursor()

        # Get latest activity and features
        ts_filter = f"AND timestamp <= '{as_of}'" if as_of else ""
        cursor.execute(f"""
            SELECT total_activity, timestamp
            FROM fact_network_activity
            WHERE grid_id = ?
            {ts_filter}
            ORDER BY timestamp DESC LIMIT 1
        """, (grid_id,))
        activity_row = cursor.fetchone()

        if not activity_row:
            return {"grid_id": grid_id, "status": "no_data"}

        current_activity, current_ts = activity_row

        # Get baseline (mean of last 7 days before current ts)
        cursor.execute(f"""
            SELECT AVG(total_activity)
            FROM fact_network_activity
            WHERE grid_id = ?
            AND timestamp < ?
            AND timestamp > datetime(?, '-7 days')
        """, (grid_id, current_ts, current_ts))
        baseline = cursor.fetchone()[0] or 0

        # Get ML risk score if available
        cursor.execute(f"""
            SELECT risk_score FROM network_risk_scores
            WHERE grid_id = ? AND timestamp = ?
            {ts_filter}
        """, (grid_id, current_ts))
        risk_row = cursor.fetchone()
        risk_score = risk_row[0] if risk_row else None

        # Get anomaly score if available
        cursor.execute(f"""
            SELECT anomaly_score FROM anomaly_scores
            WHERE grid_id = ? AND timestamp = ?
        """, (grid_id, current_ts))
        anomaly_row = cursor.fetchone()
        anomaly_score = anomaly_row[0] if anomaly_row else None

        conn.close()

        # Determine severity
        activity_ratio = current_activity / baseline if baseline > 0 else 1
        severity = "high" if activity_ratio > 1.5 or (risk_score and risk_score > 0.7) else \
                   "medium" if activity_ratio > 1.2 or (risk_score and risk_score > 0.4) else "low"

        # Load location from GeoJSON
        location = {"lat": None, "lng": None, "description": f"Grid {grid_id}"}
        if GEOJSON_PATH.exists():
            with open(GEOJSON_PATH) as f:
                geojson = json.load(f)
                for feature in geojson.get("features", []):
                    if feature["properties"].get("cellId") == grid_id:
                        coords = feature["geometry"]["coordinates"]
                        location = {"lat": coords[1], "lng": coords[0], "description": f"Grid {grid_id}"}
                        break

        return {
            "grid_id": grid_id,
            "timestamp": current_ts,
            "severity": severity,
            "severity_reason": f"Activity {activity_ratio:.2f}x baseline, risk={risk_score:.2f if risk_score else 'N/A'}",
            "evidence": {
                "current_activity": float(current_activity),
                "baseline_activity": float(baseline),
                "activity_ratio": float(activity_ratio),
                "ml_risk_score": float(risk_score) if risk_score else None,
                "anomaly_score": float(anomaly_score) if anomaly_score else None,
                "location": location
            },
            "interpretation": f"Grid {grid_id} shows {'elevated' if activity_ratio > 1.2 else 'normal'} activity relative to baseline. "
                            f"ML model {'indicates' if risk_score and risk_score > 0.5 else 'does not indicate'} high-activity risk.",
            "next_checks": [
                "Verify activity spike is not due to data quality issue",
                "Check for correlated grids in same geographic area",
                "Review customer reports from this location",
                "Inspect raw data for anomalous patterns" if anomaly_score and anomaly_score > 2 else "Continue monitoring"
            ]
        }
    except Exception as e:
        return {"grid_id": grid_id, "status": "error", "error": str(e)}


def review_anomaly(grid_id: int, timestamp: str) -> dict:
    """
    Compare rule alert, classifier output, and anomaly score for a grid.
    Explain any disagreement.

    Returns:
    {
        "grid_id": int,
        "timestamp": str,
        "rule_alert": {"triggered": bool, "reason": str},
        "classifier": {"prediction": bool, "probability": float},
        "anomaly": {"score": float, "direction": str},
        "agreement": bool,
        "disagreement_analysis": str,
        "reconciliation": str
    }
    """
    try:
        conn = sqlite3.connect(WAREHOUSE_PATH)
        cursor = conn.cursor()

        # Rule-based alert (NP3 logic)
        cursor.execute(f"""
            SELECT total_activity FROM fact_network_activity
            WHERE grid_id = ? AND timestamp = ?
        """, (grid_id, timestamp))
        activity_row = cursor.fetchone()

        if not activity_row:
            return {"grid_id": grid_id, "timestamp": timestamp, "status": "no_data"}

        current_activity = activity_row[0]

        cursor.execute(f"""
            SELECT AVG(total_activity) FROM fact_network_activity
            WHERE grid_id = ? AND timestamp < ?
            AND timestamp > datetime(?, '-7 days')
        """, (grid_id, timestamp, timestamp))
        baseline = cursor.fetchone()[0] or 0

        # Rule: activity > 1.5x baseline = HIGH_ACTIVITY alert
        rule_triggered = current_activity > baseline * 1.5

        # ML classifier output
        cursor.execute(f"""
            SELECT risk_score FROM network_risk_scores
            WHERE grid_id = ? AND timestamp = ?
        """, (grid_id, timestamp))
        risk_row = cursor.fetchone()
        risk_score = risk_row[0] if risk_row else None

        # Anomaly score
        cursor.execute(f"""
            SELECT anomaly_score FROM anomaly_scores
            WHERE grid_id = ? AND timestamp = ?
        """, (grid_id, timestamp))
        anomaly_row = cursor.fetchone()
        anomaly_score = anomaly_row[0] if anomaly_row else None

        conn.close()

        # Determine agreement
        classifier_pred = risk_score > 0.5 if risk_score else None
        anomaly_elevated = anomaly_score > 1.5 if anomaly_score else None

        agreement = (rule_triggered == classifier_pred == anomaly_elevated) if all([classifier_pred, anomaly_elevated]) else None

        disagreement_msg = ""
        if not agreement and agreement is not None:
            if rule_triggered != classifier_pred:
                disagreement_msg += f"Rule alert ({rule_triggered}) differs from classifier ({classifier_pred}). "
            if rule_triggered != anomaly_elevated:
                disagreement_msg += f"Rule alert ({rule_triggered}) differs from anomaly ({anomaly_elevated}). "

        return {
            "grid_id": grid_id,
            "timestamp": timestamp,
            "rule_alert": {
                "triggered": rule_triggered,
                "reason": f"Activity {current_activity:.0f} > {baseline * 1.5:.0f} (1.5x baseline)"
            },
            "classifier": {
                "prediction": classifier_pred,
                "probability": float(risk_score) if risk_score else None
            },
            "anomaly": {
                "score": float(anomaly_score) if anomaly_score else None,
                "direction": "above_baseline" if anomaly_score and anomaly_score > 0 else "below_baseline" if anomaly_score and anomaly_score < 0 else "neutral"
            },
            "agreement": agreement,
            "disagreement_analysis": disagreement_msg if disagreement_msg else "All signals agree",
            "reconciliation": "Investigate data quality or feature engineering if signals diverge significantly"
        }
    except Exception as e:
        return {"grid_id": grid_id, "timestamp": timestamp, "status": "error", "error": str(e)}


def test_api() -> dict:
    """
    Run the API test suite via pytest.

    Returns:
    {
        "status": "passed|failed",
        "total_tests": int,
        "passed": int,
        "failed": int,
        "errors": [{"test": str, "message": str}],
        "execution_time": float
    }
    """
    import subprocess
    import time

    try:
        start = time.time()
        result = subprocess.run(
            ["python", "-m", "pytest", "phase4/", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        elapsed = time.time() - start

        output = result.stdout + result.stderr

        # Parse pytest output for summary
        passed = output.count(" PASSED")
        failed = output.count(" FAILED")

        errors = []
        for line in output.split("\n"):
            if "FAILED" in line:
                errors.append({"test": line.split("::")[1] if "::" in line else line, "message": line})

        return {
            "status": "passed" if result.returncode == 0 else "failed",
            "total_tests": passed + failed,
            "passed": passed,
            "failed": failed,
            "errors": errors[:10],  # Limit to 10 errors
            "execution_time": elapsed,
            "output_excerpt": output[-500:] if output else "No output"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def network_health() -> dict:
    """
    Validate grain integrity on hourly_grid_summary (grain: grid_id, timestamp).

    Returns:
    {
        "status": "PASS|FAIL",
        "table": "hourly_grid_summary",
        "total_rows": int,
        "duplicates_found": int,
        "grain_validation": {
            "expected_grain": "(grid_id, timestamp)",
            "duplicate_rows": [...],
            "validation_passed": bool
        },
        "recommendation": str
    }
    """
    try:
        conn = sqlite3.connect(WAREHOUSE_PATH)
        cursor = conn.cursor()

        # Count total rows
        cursor.execute("SELECT COUNT(*) FROM fact_network_activity")
        total_rows = cursor.fetchone()[0]

        # Find duplicates on (grid_id, timestamp)
        cursor.execute("""
            SELECT grid_id, timestamp, COUNT(*) as cnt
            FROM fact_network_activity
            GROUP BY grid_id, timestamp
            HAVING cnt > 1
        """)
        duplicates = cursor.fetchall()

        conn.close()

        if duplicates:
            return {
                "status": "FAIL",
                "table": "fact_network_activity",
                "total_rows": total_rows,
                "duplicates_found": len(duplicates),
                "grain_validation": {
                    "expected_grain": "(grid_id, timestamp)",
                    "duplicate_rows": [{"grid_id": d[0], "timestamp": d[1], "count": d[2]} for d in duplicates[:5]],
                    "validation_passed": False
                },
                "recommendation": "Investigate and remove duplicate (grid_id, timestamp) rows. Data grain is violated."
            }
        else:
            return {
                "status": "PASS",
                "table": "fact_network_activity",
                "total_rows": total_rows,
                "duplicates_found": 0,
                "grain_validation": {
                    "expected_grain": "(grid_id, timestamp)",
                    "duplicate_rows": [],
                    "validation_passed": True
                },
                "recommendation": "No issues detected. Grain integrity is valid."
            }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


if __name__ == "__main__":
    # Quick test
    print("=== Pipeline Health ===")
    print(json.dumps(check_pipeline(), indent=2))
    print("\n=== Network Health ===")
    print(json.dumps(network_health(), indent=2))
