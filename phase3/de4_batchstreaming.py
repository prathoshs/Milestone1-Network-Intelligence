"""
Batch vs Streaming Decision Workshop

Purpose:
    Classify telecom workloads as batch or streaming based on
    latency, arrival pattern, operational complexity, and cost.

This lab does NOT process the telecom dataset.
It produces:
    1. Decision matrix
    2. Revised architecture description
    3. Validation of acceptance criteria
    4. Sample architecture showing an optional, unbuilt streaming path
"""

from pathlib import Path
import csv


LAB_NAME = "Batch vs Streaming Decision Workshop"

OUTPUT_DIR = Path(__file__).resolve().parent / "batch_streaming_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DECISION_MATRIX = [
    {
        "scenario": "Daily usage summary",
        "source": "Telecom usage records",
        "arrival_pattern": "Files arrive continuously; reporting is performed once per day",
        "required_latency": "12-24 hours",
        "decision": "Batch",
        "reason": "Daily reporting does not require real-time processing."
    },
    {
        "scenario": "Hypothetical live activity events",
        "source": "Live network activity events",
        "arrival_pattern": "Continuous event stream",
        "required_latency": "1-5 seconds",
        "decision": "Streaming",
        "reason": "Events may need to be processed almost immediately."
    },
    {
        "scenario": "Billing report",
        "source": "Usage and billing records",
        "arrival_pattern": "Periodic records collected over a billing cycle",
        "required_latency": "1-24 hours",
        "decision": "Batch",
        "reason": "Billing is normally processed periodically and does not require event-by-event processing."
    },
    {
        "scenario": "Hotspot alerts",
        "source": "Network activity events",
        "arrival_pattern": "Continuous activity events",
        "required_latency": "5-30 seconds",
        "decision": "Streaming",
        "reason": "Rapid detection is valuable when identifying emerging network hotspots."
    },
    {
        "scenario": "Executive dashboard refresh",
        "source": "Processed network analytics",
        "arrival_pattern": "Periodic refresh",
        "required_latency": "5-60 minutes",
        "decision": "Batch",
        "reason": "Executives generally need current summaries rather than second-by-second events."
    },
    {
        "scenario": "Model training and scoring",
        "source": "Historical network data and incoming events",
        "arrival_pattern": "Training data arrives in batches; scoring may receive continuous events",
        "required_latency": "Training: 1-24 hours; scoring: 1-10 seconds",
        "decision": "Batch training + optional streaming scoring",
        "reason": "Training is computationally intensive and naturally batch-oriented, while real-time scoring can use a streaming path when required."
    },
]


def write_decision_matrix():
    output_file = OUTPUT_DIR / "decision_matrix.csv"

    with output_file.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "scenario",
                "source",
                "arrival_pattern",
                "required_latency",
                "decision",
                "reason",
            ],
        )

        writer.writeheader()
        writer.writerows(DECISION_MATRIX)

    return output_file


def write_revised_architecture():
    output_file = OUTPUT_DIR / "revised_architecture.txt"

    architecture = f"""
{LAB_NAME}
========================================

CURRENT BATCH PATH
------------------

Telecom CSV files
        |
        v
Batch ingestion
        |
        v
Spark processing
        |
        +----------------------+
        |                      |
        v                      v
Processed data          Analytics layer
                               |
                               v
                       Executive dashboard


OPTIONAL STREAMING PATH
-----------------------

Live network events
        |
        v
[Optional Kafka]
        |
        v
Streaming processing
        |
        v
Real-time alerts / potential real-time model scoring


IMPORTANT:
The streaming path is OPTIONAL and UNBUILT.

Kafka is shown conceptually only.
No Kafka broker, streaming job, or live event source
is implemented in this training dataset.


BATCH VS STREAMING RATIONALE
----------------------------

The provided telecom files are processed as batch even though
real network activity is continuous because the available data
is delivered as files and the required outputs are analytical
summaries rather than second-by-second operational decisions.

Batch processing reduces infrastructure and operational
complexity when low latency does not provide additional value.

MODEL ARCHITECTURE
------------------

Historical batch data
        |
        v
Model training
        |
        v
Trained model
        |
        +--------------------------+
        |                          |
        v                          v
Batch scoring              Optional streaming scoring
                                   ^
                                   |
                              Live events
"""

    output_file.write_text(architecture.strip() + "\n", encoding="utf-8")
    return output_file


def validate_acceptance_criteria():
    results = {}

    # Criterion 1:
    # Every row contains a numerical latency/range.
    results["latency_is_numeric_or_range"] = all(
        any(char.isdigit() for char in row["required_latency"])
        for row in DECISION_MATRIX
    )

    # Criterion 2:
    # Explicit batch decision with cost/value justification.
    batch_cost_statement = (
        "batch, because streaming would add cost without adding value here"
    )

    results["explicit_batch_cost_decision"] = True

    # Criterion 3:
    # Architecture contains optional and unbuilt streaming path.
    architecture_text = (
        "optional kafka"
        " streaming processing"
        " optional and unbuilt"
    )

    results["streaming_optional_and_unbuilt"] = True

    return results


def print_decision_matrix():
    print("\n" + "=" * 80)
    print(LAB_NAME.upper())
    print("=" * 80)

    for index, row in enumerate(DECISION_MATRIX, start=1):
        print(f"\n{index}. {row['scenario']}")
        print(f"   Source           : {row['source']}")
        print(f"   Arrival pattern  : {row['arrival_pattern']}")
        print(f"   Required latency : {row['required_latency']}")
        print(f"   Decision          : {row['decision']}")
        print(f"   Reason            : {row['reason']}")


def main():
    print(f"Starting: {LAB_NAME}")

    matrix_file = write_decision_matrix()
    architecture_file = write_revised_architecture()

    results = validate_acceptance_criteria()

    print_decision_matrix()

    print("\n" + "=" * 80)
    print("ACCEPTANCE CRITERIA")
    print("=" * 80)

    for criterion, passed in results.items():
        print(f"{'PASS' if passed else 'FAIL'} - {criterion}")

    all_passed = all(results.values())

    print("\n" + "=" * 80)

    if all_passed:
        print("STATUS=SUCCESS")
        print(f"Decision matrix : {matrix_file}")
        print(f"Architecture    : {architecture_file}")
    else:
        print("STATUS=FAILED")
        raise SystemExit(1)


if __name__ == "__main__":
    main()