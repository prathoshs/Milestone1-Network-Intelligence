#!/usr/bin/env python3
"""
/review-anomaly wrapper

Usage: python cmd_review_anomaly.py GRID_ID TIMESTAMP
"""

import sys
import json
sys.path.insert(0, str(__file__).rsplit('/', 1)[0] + '/..')
from phase7.commands import review_anomaly

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python cmd_review_anomaly.py GRID_ID TIMESTAMP")
        print("Example: python cmd_review_anomaly.py 4821 '2013-11-04 15:00:00'")
        sys.exit(1)

    grid_id = int(sys.argv[1])
    timestamp = sys.argv[2]

    result = review_anomaly(grid_id, timestamp)

    if result.get('status') == 'no_data':
        print(f"\nNo data available for grid {grid_id} at {timestamp}\n")
        sys.exit(1)

    if result.get('status') == 'error':
        print(f"\nError: {result.get('error')}\n")
        sys.exit(1)

    print("\n" + "="*70)
    print(f"ANOMALY REVIEW: Grid {result['grid_id']} @ {result['timestamp']}")
    print("="*70)

    print("\n--- RULE-BASED ALERT (NP3) ---")
    rule = result['rule_alert']
    print(f"Triggered: {'YES' if rule['triggered'] else 'NO'}")
    print(f"Reason: {rule['reason']}")

    print("\n--- ML CLASSIFIER (Logistic Regression) ---")
    clf = result['classifier']
    if clf['prediction'] is not None:
        print(f"Prediction: {'HIGH RISK' if clf['prediction'] else 'NORMAL'}")
        print(f"Probability: {clf['probability']:.3f}")
    else:
        print("Prediction: UNAVAILABLE")

    print("\n--- ANOMALY ANALYSIS (Baseline Deviation) ---")
    anom = result['anomaly']
    if anom['score'] is not None:
        print(f"Score: {anom['score']:.2f}")
        print(f"Direction: {anom['direction'].replace('_', ' ').title()}")
    else:
        print("Score: UNAVAILABLE")

    print("\n--- SIGNAL AGREEMENT ---")
    if result['agreement'] is None:
        print("Cannot determine: Missing signals")
    elif result['agreement']:
        print("✓ All signals AGREE")
    else:
        print("✗ Signals DISAGREE")
        print(f"Analysis: {result['disagreement_analysis']}")

    print("\n--- RECONCILIATION ---")
    print(result['reconciliation'])

    print("="*70 + "\n")
