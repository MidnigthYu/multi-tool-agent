#!/bin/bash
if [ ! -f .env ]; then
    echo "Error: .env not found. Copy .env.example to .env and fill in values."
    exit 1
fi
pip install -e .
python -m core.agent_graph
