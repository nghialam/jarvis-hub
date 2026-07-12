#!/usr/bin/env python3
"""Fix app.py main block indentation."""

with open('/Users/nghialam/jarvis-hub/app.py', 'r') as f:
    content = f.read()

main_start = content.find("\n# --- Application entry point")
if main_start == -1:
    print("Could not find main block marker")
else:
    new_main_lines = [
        "\n",
        "# --- Application entry point -------------------------------------------------\n",
        "\n",
        "if __name__ == '__main__':\n",
        "    import argparse\n",
        "    parser = argparse.ArgumentParser(description='Jarvis Hub 2.0 - Market Intelligence Portal')\n",
        "    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')\n",
        "    parser.add_argument('--port', type=int, default=8100, help='Port to listen on')\n",
        "    parser.add_argument('--debug', action='store_true', help='Enable debug mode')\n",
        "    args = parser.parse_args()\n",
        "\n",
        "    print('=' * 60)\n",
        "    print('  Jarvis Hub 2.0 - Market Intelligence Portal')\n",
        "    print('=' * 60)\n",
        "\n",
        "     # Initialize services\n",
        "     _init()\n",
        "\n",
        "    print(f'\\n  Server running at http://{args.host}:{args.port}')\n",
        "    print(f'  Dashboard:      http://{args.host}:{args.port}/hub2')\n",
        "    print(f'  Health check:   http://{args.host}:{args.port}/health')\n",
        "    print('=' * 60)\n",
        "\n",
        "    app.run(\n",
        "        host=args.host,\n",
        "        port=args.port,\n",
        "        debug=args.debug,\n",
        "        threaded=True,\n",
        "     )\n",
    ]
    
    content = content[:main_start] + ''.join(new_main_lines)
    
    with open('/Users/nghialam/jarvis-hub/app.py', 'w') as f:
        f.write(content)
    
    print("Replaced main block successfully")
