#!/usr/bin/env python3
"""Patch llm_evaluation.py to handle Ollama streaming properly."""
import re

filepath = '/Users/nghialam/jarvis-hub/core/llm_evaluation.py'

with open(filepath, 'r') as f:
    content = f.read()

# Define the old streaming function block
old_func = '''def call_ollama(prompt):
     """Call Ollama for LLM analysis."""
    import requests

    ollama_url = "http://localhost:11434"
     # Use the user's model name from their profile config
    model  = "qwen3.6:35b-a3b-mxfp8"

    try:
        r = requests.post(
             "{}/v1/chat/completions".format(ollama_url),
            json={
                 "model": model,
                 "messages": [
                     {"role": "system",
                     "content": "Ban la chuyen gia phan tich tai chinh Viet Nam. Tra loi bang tieng Vietnam."},
                     {"role": "user", "content": prompt},
                 ],
                 "stream": False,
                 "options": {
                     "num_predict": 4096,
                     "temperature": 0.7,
                 },
             },
            timeout=300,
        )

        if r.status_code == 200:
            resp = r.json()
            content = (resp.get("message", {}).get("content", "") or "").strip()
            return content
        print("[EVAL] Ollama returned %s: %s" % (r.status_code, r.text[:200]))
        return None

    except requests.exceptions.Timeout:
        print("[EVAL] Timeout after 300s")
        return None
    except Exception as e:
        print("[EVAL] Error: %s" % e)
        return None'''

# Define the new streaming parser function
new_func = '''def call_ollama(prompt):
     """Call Ollama for LLM analysis. Handles streaming response from qwen3.6 models."""
    import requests

    ollama_url = "http://localhost:11434"
     # Use the user's model name from their profile config
    model  = "qwen3.6:35b-a3b-mxfp8"

    try:
        payload = {
             "model": model,
            "messages": [
                 {"role": "system",
                 "content": "Ban la chuyen gia phan tich tai chinh Viet Nam. Tra loi bang tieng Vietnam."},
                 {"role": "user", "content": prompt},
             ],
            "stream": True,  # Enable streaming since qwen3.6 streams chunks
             "options": {
                "num_predict": 4096,
                  "temperature" : 0.7,
            },
        }

         # Send request and read SSE-style line-by-line stream
        r = requests.post(
            "{}/chat".format(ollama_url),
            json=payload,
            timeout=300,
             stream=True,
        )

        if r.status_code != 200:
            print("[EVAL] Ollama returned %s: %s" % (r.status_code, r.text[:200]))
            return None

        full_text = []
         for line in r.iter_lines():
             if not line.strip():
                 continue
            try:
                chunk = json.loads(line)
                delta = chunk.get("message", {}).get("content", "")
                 if delta:  # Only collect actual text content (skip thinking/done chunks)
                     full_text.append(delta)
                  except (json.JSONDecodeError, KeyError):
                    pass  # Skip non-JSON lines

        return "".join(full_text).strip()

    except requests.exceptions.Timeout:
            print("[EVAL] Timeout after 300s")
        return None
     except Exception as e:
            print("[EVAL] Error: %s" % e)
        return None'''

if old_func in content:
    content = content.replace(old_func, new_func)
    
    # Also fix the import section if json isn't imported (it should be, let's verify)
    if 'import json' not in content.split('def call_ollama')[0].split('\n')[-10:]:
        lines_inject = content.find('import os')
        if '"json"' not in content[:lines_inject] and 'import json' not in content[:lines_inject]:
            content = content.replace('import json', 'import json\n', 1)
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    print("✅ Streaming handler patched")
else:
    print("❌ Old function text not found (already replaced or modified)")

# Validate syntax
import ast
try:
    ast.parse(content)
    print("Syntax OK")
except SyntaxError as e:
    print(f"ERROR line {e.lineno}: {e.msg}")
    lines = content.split('\n')
    start = max(0, e.lineno - 3)
    end = min(len(lines), e.lineno + 2)
    for i in range(start, end):
        marker = ">>>" if i == e.lineno - 1 else "    "
        print(f"{marker} {i+1:4d}: {lines[i][:80]}")
