

if __name__ == "__main__":
     _init()
    print("[APP] Starting Jarvis Hub Flask server on port 8100...")
    app.run(host="0.0.0.0", port=8100, debug=False, use_reloader=False)
