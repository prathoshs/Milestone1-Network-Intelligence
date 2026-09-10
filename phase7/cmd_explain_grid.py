#!/usr/bin/env python3
"""
/explain-grid wrapper

Usage: python cmd_explain_grid.py GRID_ID [--as-of TIMESTAMP]
"""

import sys
import json
sys.path.insert(0, str(__file__).rsplit('/', 1)[0] + '/..')
from phase7.commands import explain_grid

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python cmd_explain_grid.py GRID_ID [--as-of TIMESTAMP]")
        sys.exit(1)

    grid_id = int(sys.argv[1])
    as_of = None
    if "--as-of" in sys.argv:
        idx = sys.argv.index("--as-of")
        as_of = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None

    result = explain_grid(grid_id, as_of)

    if result.get('status') == 'no_data':
        print(f"\nNo data available for grid {grid_id}\n")
        sys.exit(1)

    if result.get('status') == 'error':
        print(f"\nError: {result.get('error')}\n")
        sys.exit(1)

    print("\n" + "="*70)
    print(f"GRID {result['grid_id']} ANALYSIS")
    print("="*70)

    print(f"\nTimestamp: {result.get('timestamp', 'N/A')}")
    print(f"Severity: {result['severity'].upper()}")
    print(f"Reason: {result['severity_reason']}")

    print("\n--- EVIDENCE ---")
    ev = result['evidence']
    print(f"Current Activity: {ev['current_activity']:.0f}")
    print(f"Baseline Activity: {ev['baseline_activity']:.0f}")
    print(f"Activity Ratio: {ev['activity_ratio']:.2f}x")
    if ev['ml_risk_score'] is not None:
        print(f"ML Risk Score: {ev['ml_risk_score']:.3f}")
    if ev['anomaly_score'] is not None:
        print(f"Anomaly Score: {ev['anomaly_score']:.2f}")
    if ev['location']['lat']:
        print(f"Location: ({ev['location']['lat']:.4f}, {ev['location']['lng']:.4f})")

    print("\n--- INTERPRETATION ---")
    print(result['interpretation'])

    print("\n--- NEXT CHECKS ---")
    for i, check in enumerate(result['next_checks'], 1):
        print(f"{i}. {check}")

    print("="*70 + "\n")
