"""Final comprehensive integration test for Jarvis Hub Flask app."""
import subprocess
import json
import sys


def is_json(body):
    return body and (body.strip().startswith('{') or body.strip().startswith('['))


def is_html(body):
    if not body:
        return False
    return '<!doctype' in body.lower() or '<html' in body.lower()


def get_preview(body, max_len=60):
    """Extract meaningful preview from response body."""
    if not body:
        return "(empty)"
    try:
        data = json.loads(body[:1000])
        if isinstance(data, dict):
            keys = list(data.keys())[:3]
            return f"keys={keys}"
        elif isinstance(data, list):
            return f"[{len(data)} items]"
        else:
            return str(data)[:max_len]
    except Exception:
        if is_html(body):
            return "html page"
        return body[:max_len].replace("\n", " ")


def test_http(method, path, data=None, desc=""):
    """Make HTTP request and return (success, desc, http_code, content_type, preview)."""
    cmd = ["curl", "-s", "-w", "\n%{http_code}"]

    if method == "POST":
        cmd.extend(["-X", "POST", "-H", "Content-Type: application/json"])
        if data:
            cmd.append(f"-d '{json.dumps(data)}'")
    elif method == "GET":
        cmd.extend(["-X", "GET"])

    full_url = f"http://localhost:8100{path}"
    cmd.append(full_url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        lines = result.stdout.split("\n")
        http_code = lines[-1].strip() if len(lines) >= 2 else "?"
        body = "\n".join(lines[:-1]).strip()

        content_type = "JSON" if is_json(body) else ("HTML" if is_html(body) else "OTHER")
        preview = get_preview(body) if content_type != "OTHER" else f"[HTTP {http_code}]"

        success = http_code == "200"
        return (success, desc, http_code, content_type, preview)
    except subprocess.TimeoutExpired:
        return (False, desc, "TIMEOUT", "TIMEOUT", "")
    except Exception as e:
        return (False, desc, f"EXCEPT-{str(e)[:20]}", "ERROR", str(e)[:80])


def main():
    print("=" * 75)
    print("JARVIS HUB - COMPREHENSIVE INTEGRATION TEST")
    print("=" * 75)

    # GET endpoints to test
    get_tests = [
        ("/api/search?q=ACB&limit=3", "Search (ACB)"),
        ("/api/watchlist", "Watchlist GET"),
        ("/api/articles?limit=3", "Articles (3 items)"),
        ("/api/analyze?symbol=VNM", "Analyze VNM (Vietnam stock)"),
        ("/api/crypto?coin=BTC", "Crypto BTC price"),
        ("/api/crypto?coin=ETH", "Crypto ETH price"),
        ("/api/activities?limit=3", "Activity log"),
    ]

    # POST endpoints to test
    post_tests = [
        ({"symbol": "TEST_INT", "name": "Integration Test"}, "/api/watchlist/add", "Add watchlist item"),
        ({"symbol": "TEST_INT"}, "/api/watchlist/remove", "Remove test item"),
    ]

    ok_list = []
    fail_list = []

    print("\nGET ENDPOINTS:")
    print("-" * 75)
    for i, (path, desc) in enumerate(get_tests, 1):
        success, desc_label, code, ctype, preview = test_http("GET", path, None, desc)
        if success:
            ok_list.append(desc_label)
            status_icon = "[OK]"
        else:
            fail_list.append((desc_label, code))
            status_icon = "[FAIL]"

        print(f"{status_icon} {i}. {desc_label}")
        print(f"         Path: {path}")
        print(f"         HTTP {code} | {ctype} | {preview}\n")

    # Test home page separately (expected to be HTML)
    success, _, code, ctype, preview = test_http("GET", "/", None, "Home page (/)")
    if success:
        ok_list.append("Home page")
        status_icon = "[OK]"
    else:
        fail_list.append(("Home page", code))
        status_icon = "[FAIL]"

    print(f"HOME PAGE:")
    print(f"{status_icon} Home page (/) -> HTTP {code} | {ctype}")
    if is_html(subprocess.run(["curl", "-s", "http://localhost:8100/"], capture_output=True, text=True).stdout):
        print("         (Dashboard UI - expected HTML)\n")

    print("\nPOST ENDPOINTS:")
    print("-" * 75)
    for i, (data, path, desc) in enumerate(post_tests, 1):
        success, desc_label, code, ctype, preview = test_http("POST", path, data, desc)
        if success:
            ok_list.append(desc_label)
            status_icon = "[OK]"
        else:
            fail_list.append((desc_label, code))
            status_icon = "[FAIL]"

        print(f"{status_icon} {i}. {desc_label}")
        print(f"         Path: {path}")
        print(f"         HTTP {code} | {ctype} | {preview}\n")

    # Summary
    total = len(ok_list) + len(fail_list)
    print("=" * 75)
    print("INTEGRATION TEST REPORT:")
    print(f"  Total endpoints:  {total}")
    print(f"  [OK] Passed:      {len(ok_list)}")
    print(f"  [FAIL] Failed:    {len(fail_list)}\n")

    if ok_list:
        print("PASSED:")
        for name in ok_list:
            print(f"    - {name}")

    if fail_list:
        print("\nFAILED:")
        for name, code in fail_list:
            print(f"    - {name}: HTTP {code}")

    if not fail_list:
        print("\n  No issues detected! Flask app running and responding correctly.")
    else:
        print(f"\n  WARNING: {len(fail_list)} endpoint(s) did not return HTTP 200")

    print("=" * 75)

    # Return exit code for automation
    sys.exit(0 if not fail_list else 1)


if __name__ == "__main__":
    main()
