"""
MCP server for CPA exam seat availability.

Tools:
  - run_cpa_search      : scrape Prometric and save availability_results.json
  - get_cpa_availability: read and return the latest cached results
"""

import json
import subprocess
from pathlib import Path
import sys

from mcp.server.fastmcp import FastMCP

BASE_DIR = Path(__file__).parent
RESULTS_FILE = BASE_DIR / "availability_results.json"
PYTHON_BIN = sys.executable
SEARCH_SCRIPT = BASE_DIR / "search.py"

mcp = FastMCP("cpa-availability")


@mcp.tool()
def run_cpa_search(
    exam_section: str,
    city_or_zip: str,
    state: str,
    start_date: str,
    end_date: str,
) -> str:
    """
    Search Prometric for CPA exam seat availability and save results.
    Opens a browser, fills the form, solves the captcha automatically.
    Takes 1-3 minutes.

    Args:
        exam_section: Full exam name, e.g. "Auditing and Attestation"
        city_or_zip:  City name or ZIP, e.g. "Alpharetta"
        state:        State abbreviation, e.g. "GA"
        start_date:   YYYY-MM-DD
        end_date:     YYYY-MM-DD
    """
    cmd = [
        str(PYTHON_BIN),
        str(SEARCH_SCRIPT),
        "--exam",
        exam_section,
        "--city",
        city_or_zip,
        "--state",
        state,
        "--start",
        start_date,
        "--end",
        end_date,
        "--headless",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, cwd=str(BASE_DIR)
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            return f"Search failed (exit {result.returncode}):\n{output}"
        return f"Search complete.\n{output}\n\n" + get_cpa_availability()
    except subprocess.TimeoutExpired:
        return "Search timed out after 5 minutes."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_cpa_availability() -> str:
    """Return the latest cached CPA exam seat availability from availability_results.json."""
    if not RESULTS_FILE.exists():
        return "No results yet. Call run_cpa_search first."

    with open(RESULTS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    params = data.get("search_params", {})
    lines = [
        f"Exam: {params.get('exam_section')}",
        f"Location: {params.get('location')}",
        f"Date range: {params.get('start_date')} ~ {params.get('end_date')}",
        f"Scraped at: {data.get('scraped_at')}",
        "",
    ]

    centers = data.get("centers", [])
    if not centers:
        lines.append("No available seats found.")
    else:
        for c in centers:
            lines.append(f"[{c['distance']}] {c['center']}")
            for d in c.get("available_dates", []):
                times = ", ".join(d.get("times", [])) or "(no times captured)"
                lines.append(f"  {d['date']}: {times}")
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
