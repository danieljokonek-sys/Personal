#!/usr/bin/env bash
# Briefing Bot — Quick launcher for Mac/Linux

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Setting up virtual environment for the first time..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

python main.py run
