#!/usr/bin/env python3
"""
/check-pipeline wrapper

Usage: python cmd_check_pipeline.py [--as-of TIMESTAMP]
"""

import sys
import json
sys.path.insert(0, str(__file__).rsplit('/', 1)[0] + '/..')
from phase7.commands import check_pipeline

if __name__ == "__main__":
    as_of = None
    if "--as-of" in sys.argv:
        idx = sys.argv.index("--as-of")
        as_of = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None

    result = check_pipeline(as_of)

    print("\n" + "="*60)
    print("PIPELINE HEALTH STATUS")
    print("="*60)
    print(f"Overall Status: {result.get('status', 'UNKNOWN').upper()}")
    print(f"Last Run: {result.get('last_run', 'N/A')}")
    print(f"Staleness: {result.get('staleness_hours', 'N/A')} hours")
    print(f"\nWarehouse Rows: {result.get('warehouse_rows', 0)}")
    print(f"Rejected Rows: {result.get('rejected_rows', 0)}")

    if result.get('rejected_reasons'):
        print("\nRejection Reasons:")
        for reason in result['rejected_reasons']:
            print(f"  - {reason}")

    print("\nComponent Status:")
    for component in result.get('components', []):
        print(f"  {component['name']}: {component['status']}")

    print("="*60 + "\n")

    # Return exit code based on status
    sys.exit(0 if result.get('status') == 'healthy' else 1)
