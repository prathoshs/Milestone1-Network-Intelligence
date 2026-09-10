#!/usr/bin/env python3
"""
/network-health wrapper

Usage: python cmd_network_health.py
"""

import sys
import json
sys.path.insert(0, str(__file__).rsplit('/', 1)[0] + '/..')
from phase7.commands import network_health

if __name__ == "__main__":
    result = network_health()

    print("\n" + "="*70)
    print("NETWORK HEALTH CHECK - GRAIN VALIDATION")
    print("="*70)

    status = result.get('status', 'UNKNOWN')
    print(f"\nStatus: {status}")
    print(f"Table: {result.get('table', 'N/A')}")

    if result.get('status') == 'ERROR':
        print(f"\nError: {result.get('error')}")
        print("="*70 + "\n")
        sys.exit(1)

    print(f"Total Rows: {result.get('total_rows', 0)}")
    print(f"Duplicates Found: {result.get('duplicates_found', 0)}")

    print("\n--- GRAIN VALIDATION ---")
    grain = result['grain_validation']
    print(f"Expected Grain: {grain['expected_grain']}")
    print(f"Validation Passed: {'YES' if grain['validation_passed'] else 'NO'}")

    if not grain['validation_passed'] and grain.get('duplicate_rows'):
        print("\nDuplicate (grid_id, timestamp) combinations:")
        for dup in grain['duplicate_rows']:
            print(f"  Grid {dup['grid_id']}, {dup['timestamp']}: {dup['count']} rows")

    print("\n--- RECOMMENDATION ---")
    print(result['recommendation'])

    print("="*70 + "\n")

    sys.exit(0 if result.get('status') == 'PASS' else 1)
