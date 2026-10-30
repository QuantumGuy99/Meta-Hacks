"""Files baked into the sandbox image (the chaos template; the test harness lands in RUN-1)."""

from pathlib import Path

HARNESS_DIR = Path(__file__).parent
CHAOS_TEMPLATE = (HARNESS_DIR / "chaos_template.py").read_text()
REPLAY_RUNNER = (HARNESS_DIR / "replay_runner.py").read_text()  # replaces the load runner (DEF-14)
