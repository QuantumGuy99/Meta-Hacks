"""Files baked into the sandbox image (the chaos template; the test harness lands in RUN-1)."""

from pathlib import Path

HARNESS_DIR = Path(__file__).parent
CHAOS_TEMPLATE = (HARNESS_DIR / "chaos_template.py").read_text()
