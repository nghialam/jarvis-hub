import subprocess

result = subprocess.run(
    ["/Users/nghialam/jarvis-hub/venv/bin/python", "test_integration_full.py"],
    cwd="/Users/nghialam/jarvis-hub",
    capture_output=True, text=True, timeout=120
)

print(result.stdout)

if result.returncode != 0:
    print("\n=== STDERR ===")
    for line in result.stderr.split("\n"):
        if "traceback" in line.lower() or "error" in line.lower():
            print(line)

print(f"\nExit code: {result.returncode} (0 = pass)")
