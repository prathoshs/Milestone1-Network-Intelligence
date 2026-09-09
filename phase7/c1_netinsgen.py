import json
import os
import re
import sqlite3
import time
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

# ============================================================
# C1 - Claude API - Network Insight Generator
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = (
    PROJECT_ROOT
    / "phase3"
    / "warehouse_output"
    / "network_analytics.db"
)

OUTPUT_DIR = PROJECT_ROOT / "phase7" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RESULTS_PATH = OUTPUT_DIR / "c1_network_insights.json"
REPORT_PATH = OUTPUT_DIR / "C1_Model_Selection_Rationale.md"

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1200
FEATURE_COLUMNS = [
    "avg_activity",
    "activity_growth",
    "peak_ratio",
    "variability",
    "internet_share",
]

# ============================================================
# Claude client
# ============================================================
load_dotenv()
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise RuntimeError(
        "ANTHROPIC_API_KEY was not found."
    )
client = Anthropic(api_key=api_key)

# ============================================================
# Database
# ============================================================
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================
# Evidence construction
# ============================================================
def get_evidence(grid_id, timestamp):
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT
                f.grid_id,
                f.event_time,
                (
                    COALESCE(f.sms_count, 0)
                    + COALESCE(f.call_count, 0)
                    + COALESCE(f.internet_volume, 0)
                ) AS current_activity,

                nf.avg_activity,
                nf.activity_growth,
                nf.peak_ratio,
                nf.variability,

                a.baseline_activity,
                a.anomaly_score,
                a.anomaly_direction,
                a.anomaly_flag

            FROM fact_network_activity f

            LEFT JOIN network_feature_table nf
                ON CAST(f.grid_id AS TEXT)
                    = CAST(nf.grid_id AS TEXT)
                AND REPLACE(f.event_time, 'T', ' ')
                    = REPLACE(nf.feature_timestamp, 'T', ' ')

            LEFT JOIN network_anomaly_scores a
                ON CAST(f.grid_id AS TEXT)
                    = CAST(a.grid_id AS TEXT)
                AND REPLACE(f.event_time, 'T', ' ')
                    = REPLACE(a.timestamp, 'T', ' ')

            WHERE CAST(f.grid_id AS TEXT) = ?
              AND REPLACE(f.event_time, 'T', ' ') = ?

            LIMIT 1
            """,
            (
                str(grid_id),
                timestamp.replace("T", " "),
            ),
        ).fetchone()
        if row is None:
            return None
        evidence = {
            "grid_id": str(row["grid_id"]),
            "timestamp": row["event_time"],
            "current_activity": row["current_activity"],
            "avg_activity": row["avg_activity"],
            "activity_growth": row["activity_growth"],
            "peak_ratio": row["peak_ratio"],
            "variability": row["variability"],
            "baseline_activity": row["baseline_activity"],
            "anomaly_score": row["anomaly_score"],
            "anomaly_direction": row["anomaly_direction"],
            "anomaly_flag": row["anomaly_flag"],
            "rule_alerts": [],
        }
        return evidence
    finally:
        conn.close()
# ============================================================
# Prompt
# ============================================================
def build_prompt(evidence):
    evidence_json = json.dumps(
        evidence,
        indent=2,
        allow_nan=False,
    )
    return f"""
You are assisting a Network Operations Centre.
Here is the structured evidence for one network grid cell:

{evidence_json}

Respond in exactly these four sections:

SEVERITY
Choose one of:
NORMAL
ATTENTION
HIGH

If the evidence is insufficient to determine severity,
explicitly say:
INSUFFICIENT EVIDENCE

EVIDENCE
State only observations directly supported by the supplied
evidence. Include the relevant numbers exactly as provided.

INTERPRETATION
Explain what the evidence MIGHT mean.
Clearly label this as inference.
Do not present inference as an observed fact.

NEXT CHECKS
List practical checks that a human network engineer should
perform next.

Rules:

1. These are activity measures.
2. Do not describe them as call counts, message counts,
   or MB.
3. Do NOT claim congestion, capacity exhaustion, or
   utilization problems because those measurements are not
   provided.
4. Never invent a number.
5. Never invent a measurement.
6. Every number in EVIDENCE must exist in the supplied
   evidence.
7. Keep EVIDENCE and INTERPRETATION clearly separated.
8. If an important field is missing or the evidence is
   insufficient, explicitly state that the evidence is
   insufficient and identify what additional evidence would
   be required.
9. anomaly_score is mandatory for a complete anomaly-based
   assessment. If anomaly_score is missing, the SEVERITY section
   must contain exactly:
   INSUFFICIENT EVIDENCE

   The response must explain that the anomaly score is missing
   and state what additional evidence is required.
"""
# ============================================================
# Claude API call
# ============================================================
def generate_insight(evidence):
    prompt = build_prompt(evidence)
    start = time.perf_counter()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )
    elapsed = time.perf_counter() - start
    text = response.content[0].text
    return {
        "response": text,
        "latency_seconds": round(elapsed, 3),
        "model": MODEL,
        "input_tokens": getattr(
            response.usage,
            "input_tokens",
            None,
        ),
        "output_tokens": getattr(
            response.usage,
            "output_tokens",
            None,
        ),
    }
# ============================================================
# Validation
# ============================================================
def validate_four_sections(text):
    required = [
        "SEVERITY",
        "EVIDENCE",
        "INTERPRETATION",
        "NEXT CHECKS",
    ]
    return all(section in text for section in required)

def extract_numbers(text):
    return re.findall(
        r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?%?",
        text,
    )


def validate_evidence_numbers(evidence, text):
    """
    Validate numeric claims in the EVIDENCE section.

    Dates, section numbers, and list numbering are ignored.
    Decimal values are compared numerically with tolerance so
    reasonable rounding by Claude is accepted.
    """

    if "EVIDENCE" not in text:
        return ["EVIDENCE section missing"]

    evidence_text = text.split(
        "EVIDENCE", 1
    )[1]

    if "INTERPRETATION" in evidence_text:
        evidence_text = evidence_text.split(
            "INTERPRETATION", 1
        )[0]

    supplied_numbers = []

    for value in evidence.values():
        if isinstance(value, (int, float)):
            if isinstance(value, bool):
                continue
            supplied_numbers.append(float(value))

    response_numbers = extract_numbers(
        evidence_text
    )

    unsupported = []

    for number in response_numbers:
        clean = number.rstrip("%")

        try:
            response_value = float(clean)
        except ValueError:
            continue

        # Ignore simple section/list numbering.
        if (
            response_value.is_integer()
            and 1 <= response_value <= 20
            and "." not in clean
            and "%" not in number
        ):
            continue

        matched = False

        for supplied in supplied_numbers:
            tolerance = max(
                0.01,
                abs(supplied) * 0.02,
            )

            # Percentage representation.
            if "%" in number:
                percentage_value = supplied * 100

                if abs(
                    response_value - percentage_value
                ) <= max(
                    0.1,
                    abs(percentage_value) * 0.02,
                ):
                    matched = True
                    break

            # Normal numeric representation.
            if abs(
                response_value - supplied
            ) <= tolerance:
                matched = True
                break

        if not matched:
            unsupported.append(number)

    return sorted(set(unsupported))

def validate_no_congestion_assertion(text):
    lower = text.lower()
    forbidden_patterns = [
        "there is congestion",
        "network congestion is occurring",
        "congestion is occurring",
        "congestion has occurred",
        "experiencing congestion",
        "indicates congestion",
        "indicating congestion",
    ]
    return not any(
        pattern in lower
        for pattern in forbidden_patterns
    )
# ============================================================
# Missing anomaly score experiment
# ============================================================
def run_missing_anomaly_test(evidence):
    modified = dict(evidence)
    modified.pop("anomaly_score", None)
    modified.pop("anomaly_direction", None)
    modified.pop("anomaly_flag", None)
    prompt = build_prompt(modified)
    start = time.perf_counter()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )
    elapsed = time.perf_counter() - start
    text = response.content[0].text
    detected = (
        "insufficient evidence" in text.lower()
    )
    return {
        "response": text,
        "latency_seconds": round(
            elapsed,
            3,
        ),
        "insufficiency_detected": detected,
    }
# ============================================================
# Main
# ============================================================
def main():
    print("=" * 70)
    print("C1 - Claude API - Network Insight Generator")
    print("=" * 70)
    print(f"Database: {DB_PATH}")
    print(f"Model: {MODEL}")
    # --------------------------------------------------------
    # Select five different grids
    # --------------------------------------------------------
    conn = get_connection()
    try:
        grids = conn.execute(
            """
            SELECT DISTINCT grid_id
            FROM network_feature_table
            ORDER BY CAST(grid_id AS INTEGER)
            LIMIT 5
            """
        ).fetchall()
    finally:
        conn.close()
    if len(grids) < 5:
        raise RuntimeError(
            "Fewer than five grids are available."
        )
    results = []
    # --------------------------------------------------------
    # Generate one insight for each grid
    # --------------------------------------------------------
    for grid_row in grids:
        grid_id = str(grid_row["grid_id"])
        conn = get_connection()
        try:
            timestamp_row = conn.execute(
                """
                SELECT feature_timestamp
                FROM network_feature_table
                WHERE CAST(grid_id AS TEXT) = ?
                ORDER BY feature_timestamp
                LIMIT 1
                """,
                (grid_id,),
            ).fetchone()
        finally:
            conn.close()
        if timestamp_row is None:
            continue
        timestamp = timestamp_row["feature_timestamp"]
        print()
        print(
            f"Generating insight for grid "
            f"{grid_id} at {timestamp}"
        )
        evidence = get_evidence(
            grid_id,
            timestamp,
        )
        if evidence is None:
            print("  Evidence not found.")
            continue
        result = generate_insight(evidence)
        response_text = result["response"]
        four_sections = validate_four_sections(
            response_text
        )
        unsupported_numbers = validate_evidence_numbers(
            evidence,
            response_text,
        )
        no_congestion = (
            validate_no_congestion_assertion(
                response_text
            )
        )
        print(
            f"  Latency: "
            f"{result['latency_seconds']} seconds"
        )
        print(
            f"  Four sections: "
            f"{four_sections}"
        )
        print(
            f"  Unsupported numbers: "
            f"{unsupported_numbers}"
        )
        print(
            f"  No unsupported congestion assertion: "
            f"{no_congestion}"
        )
        results.append(
            {
                "grid_id": grid_id,
                "timestamp": timestamp,
                "evidence": evidence,
                "model": result["model"],
                "latency_seconds": result[
                    "latency_seconds"
                ],
                "input_tokens": result[
                    "input_tokens"
                ],
                "output_tokens": result[
                    "output_tokens"
                ],
                "response": response_text,
                "validation": {
                    "four_sections": four_sections,
                    "unsupported_numbers": (
                        unsupported_numbers
                    ),
                    "no_congestion_assertion": (
                        no_congestion
                    ),
                },
            }
        )
    # --------------------------------------------------------
    # Missing anomaly score test
    # --------------------------------------------------------
    if results:
        print()
        print(
            "Running missing anomaly score "
            "insufficiency test..."
        )
        missing_test = run_missing_anomaly_test(
            results[0]["evidence"]
        )
        print(
            "  Explicit insufficiency detected:",
            missing_test[
                "insufficiency_detected"
            ],
        )
    else:
        missing_test = None
    # --------------------------------------------------------
    # Save results
    # --------------------------------------------------------
    output = {
        "lab": "C1 - Claude API - Network Insight Generator",
        "model": MODEL,
        "results": results,
        "missing_anomaly_test": missing_test,
    }
    RESULTS_PATH.write_text(
        json.dumps(
            output,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    # --------------------------------------------------------
    # Model selection rationale
    # --------------------------------------------------------
    report = f"""# C1 — Model Selection Rationale

## Selected Model

**Model:** `{MODEL}`

## Reason for Selection

Claude Haiku 4.5 is used as the primary model for this
lab because the task is structured evidence-to-explanation
generation rather than unrestricted reasoning.

The model receives a curated evidence object and produces:

- Severity
- Evidence
- Interpretation
- Next Checks

The integration therefore prioritizes:

1. Low latency
2. Lower API cost
3. Sufficient reasoning for structured operational explanation
4. Reliable instruction following

A larger Claude model could provide deeper reasoning, but
would generally increase cost and latency. For this C1 task,
the evidence is already structured by the ML pipeline, so a
smaller model is appropriate for the first implementation.

## Cost Consideration

The API response records input and output token counts in:

`c1_network_insights.json`

Actual cost should be calculated using the current Anthropic
pricing applicable to the selected model at the time of
submission.

## Latency Consideration

Each API call records:

`latency_seconds`

This allows the learner to compare response speed across
model choices.

## Reasoning Depth

The task does not require long-form autonomous reasoning.
Claude's role is to transform structured ML evidence into an
operations-friendly explanation while maintaining the
observation/inference boundary.

## Evidence Grounding

The prompt explicitly requires:

- No invented numbers
- No unsupported measurements
- No congestion claims
- Clear separation between evidence and interpretation
- Explicit insufficiency when important evidence is missing

## Validation

The implementation tests:

- Five different grids
- Four required response sections
- Unsupported numbers
- Unsupported congestion assertions
- Missing anomaly score / insufficient evidence behavior
"""

    REPORT_PATH.write_text(
        report,
        encoding="utf-8",
    )
    print()
    print("=" * 70)
    print("C1 completed")
    print("=" * 70)
    print(f"Results: {RESULTS_PATH}")
    print(f"Report:  {REPORT_PATH}")
    print(f"Grids tested: {len(results)}")
    if missing_test:
        print(
            "Missing anomaly test:",
            missing_test[
                "insufficiency_detected"
            ],
        )

if __name__ == "__main__":
    main()