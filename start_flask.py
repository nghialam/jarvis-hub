#!/usr/bin/env python3
"""Start Jarvis Hub Flask server on port 8100."""
import sys
sys.path.insert(0, '/Users/nghialam/jarvis-hub')

# Load and run
import app as flask_app

# JH3.0: run the full bootstrap (config, DB, blueprints, security, schedulers)
# before serving. Importing the module alone only defines _init(); it does not
# execute it unless we call it here (the app.py __main__ block does not run
# when this file is the entry point).
flask_app._init()

flask_app.app.run(host='0.0.0.0', port=8100, use_reloader=False)
