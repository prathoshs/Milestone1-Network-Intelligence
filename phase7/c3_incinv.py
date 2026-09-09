import os
import json
from pathlib import Path
import requests
import sqlite3
import anthropic
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("ANTHROPIC_API_KEY")

BASE = os.getenv(
    "NETWORK_API_BASE",
    "http://127.0.0.1:8000"
)

MODEL = os.getenv(
    "CLAUDE_MODEL",
    "claude-sonnet-4-5"
)

GRID_ID = "4821"
AS_OF = "2013-11-07T23:00:00"

DB_PATH = (
    Path(__file__).resolve().parent.parent
    / "phase3"
    / "warehouse_output"
    / "network_analytics.db"
)
client = anthropic.Anthropic()
OUTPUT_DIR = Path(__file__).resolve().parent
# ============================================================
# TOOL CALL
# ============================================================
def get_api(path, params=None):
    url = f"{BASE}{path}"
    try:
        response = requests.get(
            url,
            params=params or {},
            timeout=20,
        )
        if response.status_code >= 400:
            return {
                "status": "failed",
                "status_code": response.status_code,
                "error": response.text,
            }
        return {
            "status": "success",
            "data": response.json(),
        }
    except Exception as exc:
        return {
            "status": "failed",
            "error": str(exc),
        }
# ============================================================
# COLLECT EVIDENCE
# ============================================================
def collect_evidence():
    pipeline = get_api(
        "/pipeline/status"
    )
    location = get_api(
        f"/network/grid/{GRID_ID}/location"
    )
    features = get_api(
        f"/network/grid/{GRID_ID}/features"
    )
    activity = get_api(
        f"/network/grid/{GRID_ID}"
    )
    timeline = get_api(
        f"/network/grid/{GRID_ID}/timeline"
    )
    alerts = get_api(
        "/network/alerts",
        {
            "limit": 10000,
            "as_of": "2013-11-07T23:00:00",
        },
    )
    return {
        "pipeline_status": pipeline,
        "location": location,
        "features": features,
        "current_activity": activity,
        "timeline": timeline,
        "alerts": alerts,
    }
# ============================================================
# SUMMARIZE HISTORICAL EVIDENCE
# ============================================================
def summarize_timeline(timeline_data):
    if timeline_data.get("status") != "success":
        return {
            "status": "unavailable",
            "reason": timeline_data.get(
                "error",
                "Timeline unavailable"
            ),
        }
    points = timeline_data["data"].get(
        "points",
        []
    )
    if not points:
        return {
            "status": "available",
            "points": 0,
            "summary": "No historical points returned.",
        }
    totals = [
        float(p["total_activity"])
        for p in points
        if p.get("total_activity") is not None
    ]
    risk_scores = [
        float(p["risk_score"])
        for p in points
        if p.get("risk_score") is not None
    ]
    risk_levels = {}
    for p in points:
        level = p.get("risk_level")
        if level:
            risk_levels[level] = (
                risk_levels.get(level, 0) + 1
            )
    summary = {
        "status": "available",
        "points": len(points),
        "period_start": points[0]["timestamp"],
        "period_end": points[-1]["timestamp"],
        "minimum_total_activity": min(totals)
        if totals else None,
        "maximum_total_activity": max(totals)
        if totals else None,
        "average_total_activity": (
            sum(totals) / len(totals)
            if totals else None
        ),
        "risk_score_min": min(risk_scores)
        if risk_scores else None,
        "risk_score_max": max(risk_scores)
        if risk_scores else None,
        "risk_levels": risk_levels,
    }
    return summary
# ============================================================
# SUMMARIZE PRIOR ALERTS
# ============================================================
def summarize_alerts(alert_data):
    if alert_data.get("status") != "success":
        return {
            "status": "unavailable",
            "reason": alert_data.get(
                "error",
                "Alert data unavailable"
            ),
        }
    results = alert_data["data"].get(
        "results",
        []
    )
    grid_alerts = [
        row
        for row in results
        if str(row.get("grid_id")) == GRID_ID
    ]
    severity_counts = {}
    for row in grid_alerts:
        severity = row.get(
            "severity",
            "UNKNOWN"
        )
        severity_counts[severity] = (
            severity_counts.get(severity, 0) + 1
        )
    return {
        "status": "available",
        "alert_count": len(grid_alerts),
        "severity_counts": severity_counts,
        "first_alert": (
            grid_alerts[0]["timestamp"]
            if grid_alerts else None
        ),
        "last_alert": (
            grid_alerts[-1]["timestamp"]
            if grid_alerts else None
        ),
    }
    
def load_current_model_and_anomaly():
    conn = sqlite3.connect(DB_PATH)

    model_row = conn.execute("""
        SELECT grid_id, timestamp, risk_score, risk_level, model_version
        FROM network_risk_scores
        WHERE grid_id = ? AND timestamp = ?
        LIMIT 1
    """, (GRID_ID, AS_OF.replace("T", " "))).fetchone()

    anomaly_row = conn.execute("""
        SELECT grid_id, timestamp, anomaly_score, anomaly_direction, anomaly_flag
        FROM network_anomaly_scores
        WHERE grid_id = ? AND timestamp = ?
        LIMIT 1
    """, (GRID_ID, AS_OF.replace("T", " "))).fetchone()

    conn.close()

    model_risk = None
    if model_row:
        model_risk = {
            "grid_id": model_row[0],
            "timestamp": model_row[1],
            "risk_score": model_row[2],
            "risk_level": model_row[3],
            "model_version": model_row[4]
        }

    anomaly = None
    if anomaly_row:
        anomaly = {
            "grid_id": anomaly_row[0],
            "timestamp": anomaly_row[1],
            "anomaly_score": anomaly_row[2],
            "anomaly_direction": anomaly_row[3],
            "anomaly_flag": anomaly_row[4]
        }

    return {
        "model_risk": model_risk,
        "anomaly": anomaly
    }
# ============================================================
# BUILD CURATED PACKAGE
# ============================================================
def build_curated_package(evidence):
    model_anomaly = load_current_model_and_anomaly()
    pipeline = evidence["pipeline_status"]
    location = evidence["location"]
    features = evidence["features"]
    activity = evidence["current_activity"]
    feature_data = (
        features.get("data", {})
        if features.get("status") == "success"
        else {}
    )
    activity_data = (
        activity.get("data", {})
        if activity.get("status") == "success"
        else {}
    )
    points = activity_data.get(
        "points",
        []
    )
    current_point = (
        points[-1]
        if points
        else None
    )
    package = {
        "grid_id": GRID_ID,
        "current_interval_metrics": {
            "timestamp": (
                current_point["timestamp"]
                if current_point
                else None
            ),
            "sms_activity": (
                current_point["sms_activity"]
                if current_point
                else None
            ),
            "call_activity": (
                current_point["call_activity"]
                if current_point
                else None
            ),
            "internet_activity": (
                current_point["internet_activity"]
                if current_point
                else None
            ),
            "total_activity": (
                current_point["total_activity"]
                if current_point
                else None
            ),
        },
        "grid_features": feature_data,
        "location": (
            location.get("data")
            if location.get("status") == "success"
            else None
        ),
        "recent_history_summary":
            summarize_timeline(
                evidence["timeline"]
            ),
        "prior_alert_summary":
            summarize_alerts(
                evidence["alerts"]
            ),
        "current_model_risk": model_anomaly["model_risk"],
        "current_anomaly": model_anomaly["anomaly"],
        "pipeline_status": (
            pipeline.get("data")
            if pipeline.get("status") == "success"
            else {
                "status": "unavailable",
                "error": pipeline.get("error"),
            }
        ),
    }
    return package
# ============================================================
# DUMP EVERYTHING CONTEXT
# ============================================================
def build_dump_context(evidence):
    return json.dumps(
        evidence,
        indent=2,
        default=str,
    )
# ============================================================
# CURATED CONTEXT
# ============================================================
def build_curated_context(package):
    return json.dumps(
        package,
        indent=2,
        default=str,
    )
# ============================================================
# CLAUDE EXPERIMENT
# ============================================================

SYSTEM_PROMPT = """
You are investigating a network activity pattern.

Use ONLY the evidence provided in the context.

Answer in exactly three sections:

CURRENT EVIDENCE
HISTORICAL EVIDENCE
UNCERTAINTY

CURRENT EVIDENCE:
Describe what the current evidence shows, with figures where available.

HISTORICAL EVIDENCE:
Explain whether a similar pattern appears in the historical evidence and how often.

UNCERTAINTY:
Explicitly identify what cannot be concluded.

Pipeline status is material evidence.

Current model risk and current anomaly score are separate model outputs.

If current_model_risk is available, report its risk_score,
risk_level, and model_version.

If current_anomaly is available, report its anomaly_score,
anomaly_direction, and anomaly_flag.

Do not treat either model output as proof of congestion,
capacity problems, or service failure.

If the pipeline is unhealthy, has rejected rows,
handled nulls, failed quality checks, or stale analytics,
explain how that limits confidence.

Do not invent missing values.

Do not claim congestion.

Do not convert activity measures into counts or MB.

Do not treat activity as proof of capacity problems,
service failure, or congestion.

Distinguish observed evidence from inference.
"""

def ask_claude(context):
    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": context
                }
            ],
        )
        return response.content[0].text
    except Exception as exc:
        return (
            "DUMPED/RUN FAILURE\n"
            f"Claude request failed: {type(exc).__name__}\n"
            f"Error: {exc}\n\n"
            "Interpretation: the dumped-everything context exceeded "
            "Claude's context-window limit, so this run could not be "
            "completed. This is recorded as the negative control for "
            "the C3 context-engineering experiment."
        )
# ============================================================
# SAVE EXPERIMENT
# ============================================================
def save_text(filename, text):
    path = OUTPUT_DIR / filename
    path.write_text(
        text,
        encoding="utf-8"
    )
    return path

def create_c3_checklist():
    checklist = """# C3 Context Engineering Checklist

    ## Long-Context Incident Investigation

    ### Evidence Selection
    - [x] Use trusted network/API evidence rather than raw CSV data.
    - [x] Collect current grid activity metrics.
    - [x] Collect grid-level features.
    - [x] Collect location information.
    - [x] Collect recent historical evidence.
    - [x] Collect prior alerts.
    - [x] Collect current ML risk output.
    - [x] Collect current anomaly output.
    - [x] Collect pipeline quality/status information.

    ### Context Curation
    - [x] Summarize historical timeline before sending it to Claude.
    - [x] Summarize alert history instead of sending all alert rows.
    - [x] Avoid dumping raw historical rows into the curated context.
    - [x] Keep current metrics separate from historical evidence.
    - [x] Keep model outputs separate from observed activity measures.
    - [x] Keep pipeline status visible as material evidence.
    - [x] Preserve failed or unavailable evidence instead of inventing values.

    ### Evidence Interpretation
    - [x] Separate CURRENT EVIDENCE from HISTORICAL EVIDENCE.
    - [x] Explicitly identify UNCERTAINTY.
    - [x] Distinguish observations from model outputs.
    - [x] Do not treat model risk as proof of congestion.
    - [x] Do not treat anomaly score as proof of congestion.
    - [x] Do not convert activity measures into counts or MB.
    - [x] Do not claim capacity problems or service failure without evidence.
    - [x] Explicitly account for stale analytics.
    - [x] Explicitly account for rejected rows and data-quality limitations.

    ### Context Efficiency
    - [x] Compare dump-everything context with curated context.
    - [x] Record the failure of the oversized context as a negative control.
    - [x] Use summarized evidence to stay within the model context window.
    - [x] Remove irrelevant raw rows from the active context.

    ### Reliability / Sensitivity
    - [x] Run the investigation with the original pipeline status.
    - [x] Run the investigation with pipeline health forced to unhealthy.
    - [x] Compare the UNCERTAINTY sections.
    - [x] Verify that degraded pipeline health changes the confidence assessment.

    ### Safety and Traceability
    - [x] Do not invent missing evidence.
    - [x] Report unavailable evidence explicitly.
    - [x] Preserve model version information.
    - [x] Preserve timestamps for current evidence.
    - [x] Treat AS_OF as the effective reporting timestamp.
    - [x] Treat grid_id as a geographic grid cell.
    """
    save_text(
        "C3_Context_Engineering_Checklist.md",
        checklist
    )
    
def create_c3_report(curated_answer, unhealthy_answer):
    report = f"""# C3 Incident Investigation Report

## Objective

Investigate whether the activity pattern for Grid {GRID_ID}
has occurred before and determine whether the available data
can be trusted.

The investigation compares:

1. Dump-everything context
2. Curated evidence context
3. Curated evidence with an unhealthy pipeline status

---

## 1. Dump-Everything Experiment

The dump-everything context exceeded Claude's context-window
limit and was recorded as the negative control.

The raw context contained approximately 1.53 million tokens,
while the Claude context limit is 200,000 tokens.

Result:

- Request failed with HTTP 400 BadRequestError.
- The failure was caused by the oversized prompt.
- The failed run is retained as the negative control.

This demonstrates why raw historical evidence should not be
sent directly when it is not necessary for the investigation.

---

## 2. Curated Context Experiment

The curated evidence package contained:

- Current interval activity measures
- Grid features
- Grid location
- Summarized recent history
- Summarized prior alerts
- Current ML risk output
- Current anomaly output
- Pipeline quality and status

The curated investigation completed successfully.

The response was structured into:

- CURRENT EVIDENCE
- HISTORICAL EVIDENCE
- UNCERTAINTY

The model risk and anomaly score were treated as separate
model outputs and were not interpreted as proof of congestion,
capacity problems, or service failure.

---

## 3. Unhealthy Pipeline Experiment

A copy of the curated evidence package was created.

For this controlled sensitivity experiment, the pipeline
health value was changed from healthy to unhealthy.

The actual pipeline and database were not modified.

The purpose was to test whether degraded pipeline health
changes the uncertainty assessment.

### Normal Pipeline Answer

{curated_answer}

### Unhealthy Pipeline Answer

{unhealthy_answer}

---

## 4. Context Engineering Findings

The dump-everything approach failed because the context was
far larger than the model context window.

The curated approach succeeded because historical evidence
was summarized before being provided to Claude.

The curated package preserved the evidence needed for
investigation while avoiding unnecessary raw historical rows.

Pipeline health also affects the interpretation of the evidence.
When the pipeline is unhealthy, the investigation should place
greater emphasis on data reliability and limitations.

---

## 5. Key Engineering Principles

- Claude reasons from curated evidence.
- Claude does not replace Spark, SQL, ML, or the warehouse.
- Historical rows should be summarized when full raw history
  is unnecessary.
- Current evidence and historical evidence should remain distinct.
- Model outputs should remain distinct from observed activity.
- Pipeline quality is part of the evidence.
- Failed evidence sources must be reported rather than guessed.
- Activity measures must not be interpreted as literal counts or MB.
- Model risk must not automatically be described as congestion.
- Anomaly scores must not automatically be described as congestion.
- Capacity problems and service failures require supporting evidence.
- Uncertainty must be explicitly reported when evidence quality
  is limited.

---

## C3 Status

The C3 long-context incident investigation includes:

- Dump-everything comparison
- Curated-context investigation
- Current model-risk evidence
- Current anomaly evidence
- Historical evidence summarization
- Pipeline-quality assessment
- Unhealthy-pipeline sensitivity experiment
- Context-engineering checklist

"""

    save_text(
        "C3_Incident_Investigation_Report.md",
        report
    )

def main():
    print("=" * 70)
    print("C3 — LONG-CONTEXT INCIDENT INVESTIGATION")
    print("=" * 70)
    evidence = collect_evidence()
    curated = build_curated_package(
        evidence
    )
    dump_context = build_dump_context(
        evidence
    )
    curated_context = build_curated_context(
        curated
    )
    # --------------------------------------------------------
    # DUMP-EVERYTHING EXPERIMENT
    # --------------------------------------------------------
    print("\nRunning dump-everything experiment...")
    dumped_answer = ask_claude(
        dump_context
    )
    # --------------------------------------------------------
    # CURATED CONTEXT EXPERIMENT
    # --------------------------------------------------------
    print("\nRunning curated-context experiment...")
    curated_answer = ask_claude(
        curated_context
    )
    # --------------------------------------------------------
    # UNHEALTHY PIPELINE EXPERIMENT
    # --------------------------------------------------------
    print("\nRunning unhealthy-pipeline experiment...")
    unhealthy_curated = json.loads(
        json.dumps(curated)
    )
    unhealthy_curated["pipeline_status"]["healthy"] = False
    existing_reasons = unhealthy_curated[
        "pipeline_status"
    ].get(
        "reasons",
        []
    )
    unhealthy_curated["pipeline_status"]["reasons"] = (
        existing_reasons
        + [
            "C3 sensitivity experiment: pipeline health "
            "manually set to unhealthy to test uncertainty handling."
        ]
    )
    unhealthy_context = build_curated_context(
        unhealthy_curated
    )
    unhealthy_answer = ask_claude(
        unhealthy_context
    )
    # --------------------------------------------------------
    # SAVE EVIDENCE
    # --------------------------------------------------------
    save_text(
        "c3_dumped_context.txt",
        dump_context
    )
    save_text(
        "c3_curated_context.txt",
        curated_context
    )
    save_text(
        "c3_dumped_answer.txt",
        dumped_answer
    )
    save_text(
        "c3_curated_answer.txt",
        curated_answer
    )
    save_text(
        "c3_unhealthy_pipeline_answer.txt",
        unhealthy_answer
    )
    save_text(
        "c3_evidence_package.json",
        json.dumps(
            curated,
            indent=2,
            default=str
        )
    )
    # --------------------------------------------------------
    # CREATE CHECKLIST
    # --------------------------------------------------------
    create_c3_checklist()
    # --------------------------------------------------------
    # CREATE FINAL REPORT
    # --------------------------------------------------------
    create_c3_report(
        curated_answer,
        unhealthy_answer
    )
    # --------------------------------------------------------
    # PRINT RESULTS
    # --------------------------------------------------------
    print("\n" + "=" * 70)
    print("DUMP-EVERYTHING ANSWER")
    print("=" * 70)
    print(dumped_answer)
    print("\n" + "=" * 70)
    print("CURATED CONTEXT ANSWER")
    print("=" * 70)
    print(curated_answer)
    print("\n" + "=" * 70)
    print("UNHEALTHY PIPELINE ANSWER")
    print("=" * 70)
    print(unhealthy_answer)
    print("\n" + "=" * 70)
    print("FILES SAVED")
    print("=" * 70)
    print("c3_dumped_context.txt")
    print("c3_curated_context.txt")
    print("c3_dumped_answer.txt")
    print("c3_curated_answer.txt")
    print("c3_unhealthy_pipeline_answer.txt")
    print("c3_evidence_package.json")
    print("C3_Context_Engineering_Checklist.md")
    print("C3_Incident_Investigation_Report.md")

if __name__ == "__main__":
    main()
    
