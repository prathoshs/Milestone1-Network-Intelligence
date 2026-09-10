#!/usr/bin/env python3
"""
/test-api wrapper

Usage: python cmd_test_api.py
"""

import sys
import json
sys.path.insert(0, str(__file__).rsplit('/', 1)[0] + '/..')
from phase7.commands import test_api

if __name__ == "__main__":
    result = test_api()

    print("\n" + "="*70)
    print("API TEST SUITE RESULTS")
    print("="*70)

    status = result.get('status', 'UNKNOWN').upper()
    print(f"\nStatus: {status}")
    print(f"Execution Time: {result.get('execution_time', 0):.2f}s")

    if result.get('status') == 'error':
        print(f"\nError: {result.get('error')}")
        print("="*70 + "\n")
        sys.exit(1)

    print(f"\nTotal Tests: {result.get('total_tests', 0)}")
    print(f"Passed: {result.get('passed', 0)}")
    print(f"Failed: {result.get('failed', 0)}")

    if result.get('failed', 0) > 0:
        print("\n--- FAILED TESTS ---")
        for i, error in enumerate(result.get('errors', []), 1):
            print(f"{i}. {error.get('test', 'Unknown')}")
            if error.get('message'):
                msg = error['message'][:120] + "..." if len(error['message']) > 120 else error['message']
                print(f"   {msg}")

    if result.get('output_excerpt'):
        print("\n--- LAST OUTPUT ---")
        print(result['output_excerpt'])

    print("="*70 + "\n")

    sys.exit(0 if result.get('status') == 'passed' else 1)
