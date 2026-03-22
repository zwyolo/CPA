#!/bin/bash
set -e

echo "=== CPA Exam Availability Checker Setup ==="

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo ""
echo "Setup complete! To run:"
echo "  source venv/bin/activate"
echo "  python search.py"
