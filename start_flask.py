#!/usr/bin/env python3
"""Start Jarvis Hub Flask server on port 8100."""
import sys
sys.path.insert(0, '/Users/nghialam/jarvis-hub')

# Load and run
import app as flask_app
flask_app.app.run(host='0.0.0.0', port=8100, use_reloader=False)
