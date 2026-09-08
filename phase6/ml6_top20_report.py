from pathlib import Path
import sqlite3
from datetime import datetime


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DB_PATH = (
    PROJECT_ROOT
    / "phase3"
    / "warehouse_output"
    / "network_analytics.db"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "phase6"
    / "ML6_Top20_Operational_Attention_Report.md"
)

LOG_PATH = (
    PROJECT_ROOT
    / "phase6"
    / "ML6_Top20_Operational_Attention_Report.log"
)

MODEL_VERSION = "ML3-LightGBM-v1"


def write_log(lines):
    LOG_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main():
    start_time = datetime.now()

    log_lines = [
        "=" * 70,
        "ML6 Top-20 Operational Attention Report",
        "=" * 70,
        f"Start time: {start_time.isoformat()}",
        f"Database: {DB_PATH}",
        f"Report: {REPORT_PATH}",
        f"Model version: {MODEL_VERSION}",
    ]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute(
            """
            SELECT
                r.grid_id,
                r.timestamp,
                r.risk_score,
                r.risk_level,
                r.model_version,
                f.avg_activity,
                f.activity_growth,
                f.peak_ratio,
                f.variability,
                f.internet_share
            FROM network_risk_scores r
            LEFT JOIN network_feature_table f
                ON r.grid_id = f.grid_id
                AND r.timestamp = REPLACE(
                    f.feature_timestamp,
                    'T',
                    ' '
                )
            WHERE r.model_version = ?
            ORDER BY
                r.risk_score DESC,
                r.timestamp DESC
            LIMIT 20
            """,
            (MODEL_VERSION,),
        ).fetchall()

    except Exception as exc:
        log_lines.append(
            f"ERROR: {type(exc).__name__}: {exc}"
        )
        log_lines.append(
            f"End time: {datetime.now().isoformat()}"
        )
        write_log(log_lines)
        raise

    finally:
        conn.close()

    lines = [
        "# ML6 Top-20 Operational Attention Report",
        "",
        "## Purpose",
        "",
        "This report identifies the twenty grid-time observations "
        "with the highest model-based operational attention scores.",
        "",
        "**Important:** The risk score represents the ML3 LightGBM "
        "model's probability of HIGH_ACTIVITY in the next hour. "
        "It is not a direct prediction of congestion, capacity "
        "failure, or service failure.",
        "",
        "## Top 20 Operational Attention",
        "",
        "| Rank | Grid | Timestamp | Risk Score | "
        "Attention Level | Reason |",
        "|---:|---|---|---:|---|---|",
    ]

    for rank, row in enumerate(rows, start=1):
        grid_id = row["grid_id"]
        timestamp = row["timestamp"]
        score = row["risk_score"]
        level = row["risk_level"]

        avg_activity = row["avg_activity"]
        activity_growth = row["activity_growth"]
        peak_ratio = row["peak_ratio"]
        variability = row["variability"]
        internet_share = row["internet_share"]

        if avg_activity is not None:
            reason = (
                f"High next-hour activity attention; "
                f"avg activity={avg_activity:.2f}, "
                f"activity growth={activity_growth:.2f}, "
                f"peak ratio={peak_ratio:.2f}, "
                f"variability={variability:.2f}, "
                f"internet share={internet_share:.2%}"
            )
        else:
            reason = (
                "High next-hour activity attention based on "
                "the ML3 LightGBM risk score."
            )

        lines.append(
            f"| {rank} | {grid_id} | {timestamp} | "
            f"{float(score):.6f} | {level} | {reason} |"
        )

    lines.extend(
        [
            "",
            "## Model Information",
            "",
            f"Model version: `{MODEL_VERSION}`",
            "",
            "Model type: `LightGBM Binary Classifier`",
            "",
            "Prediction target: `HIGH_ACTIVITY` in the next hour",
            "",
            "Model features:",
            "",
            "- `avg_activity`",
            "- `activity_growth`",
            "- `peak_ratio`",
            "- `variability`",
            "- `internet_share`",
            "- `current_activity`",
            "- `previous_hour_activity`",
            "- `rolling_3h_activity`",
            "- `rolling_6h_activity`",
            "- `activity_change`",
            "- `activity_change_pct`",
            "",
            "## Operational Interpretation",
            "",
            "These observations are operational attention candidates. "
            "Higher scores indicate that the trained ML3 LightGBM model "
            "assigns a higher probability to HIGH_ACTIVITY in the "
            "following hour.",
            "",
            "The feature values provide context for prioritization. "
            "They do not by themselves establish congestion, a "
            "capacity failure, or a service failure.",
            "",
            "The ranking is based on the persisted ML6 risk scores "
            "generated from the finalized ML3 LightGBM model.",
        ]
    )

    REPORT_PATH.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    end_time = datetime.now()

    log_lines.extend(
        [
            "",
            "=" * 70,
            "TOP-20 OPERATIONAL ATTENTION RECORDS",
            "=" * 70,
            "",
            f"{'Rank':<5} "
            f"{'Grid ID':<12} "
            f"{'Timestamp':<20} "
            f"{'Risk Score':<12} "
            f"{'Risk Level':<12}",
            "-" * 70,
        ]
    )

    for rank, row in enumerate(rows, start=1):
        log_lines.append(
            f"{rank:<5} "
            f"{str(row['grid_id']):<12} "
            f"{str(row['timestamp']):<20} "
            f"{float(row['risk_score']):<12.6f} "
            f"{str(row['risk_level']):<12}"
        )

    log_lines.extend(
        [
            "",
            "=" * 70,
            "RUN SUMMARY",
            "=" * 70,
            f"Records retrieved: {len(rows)}",
            f"Report records written: {len(rows)}",
            f"Report written successfully: {REPORT_PATH}",
            f"Log written: {LOG_PATH}",
            f"End time: {end_time.isoformat()}",
            "Status: SUCCESS",
            "=" * 70,
        ]
    )

    write_log(log_lines)

    print(
        f"Report written: {REPORT_PATH}"
    )

    print(
        f"Log written: {LOG_PATH}"
    )

    print(
        f"Top-20 operational attention records: {len(rows)}"
    )

    print(
        f"Model version: {MODEL_VERSION}"
    )


if __name__ == "__main__":
    main()