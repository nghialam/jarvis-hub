#!/usr/bin/env python3
"""Batch script to update all 17 cron jobs with structured /goal prompts.
Usage: python3 ~/jarvis-hub/scripts/cron_prompts_v2.py
"""

import json as _json
from datetime import datetime
import os, sys

# Read from stdin or default file
jobs_file = os.path.expanduser("~/.hermes/scripts/_cron_updates_v2.json")

if os.path.exists(jobs_file):
    with open(jobs_file) as f:
        updates = json.load(f)
else:
    print("ERROR: No update data found.")
    sys.exit(1)

# This script should be run from within Python to call the cronjob tool.
# Since we can't invoke tools directly from a bash script,
# this is just a placeholder — real update happens via cronjob(action='update') calls.

print("Jobs file loaded. Proceed to manual cronjob updates.")
for name in updates:
    print(f"  {name}")
