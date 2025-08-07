#!/bin/bash
# Run the Super Gemini Flask application with proper Python path

export PYTHONPATH=/home/user/.local/lib/python3.12/site-packages:$PYTHONPATH
python3 app.py "$@"