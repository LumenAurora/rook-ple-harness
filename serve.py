"""WebSocket entry point for the PLE agent harness.

The evaluator starts this file once per task. All orchestration lives in
harness.py; the tool-calling engine lives in engine.py.
"""

import taskbridge

from harness import solve

if __name__ == "__main__":
  taskbridge.run(solve)
