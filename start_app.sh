#!/bin/bash
# Start the app with the correct toolbox URL

export TOOLBOX_URL=https://toolbox-zchpgeskka-uc.a.run.app
export PYTHONPATH=/home/user/.local/lib/python3.12/site-packages:$PYTHONPATH
echo "Starting app with TOOLBOX_URL=$TOOLBOX_URL"
echo "Python path configured for Flask and dependencies"
python3 app.py