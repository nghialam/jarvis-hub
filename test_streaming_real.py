#!/usr/bin/env python3
"""Test streaming with real LLM prompt from jarvis hub pipeline."""
import sys, json, os
sys.path.insert(0, '/Users/nghialam/jarvis-hub')

from core.db import Database
import requests

print("=" * 60)
print("Testing STREAMING parser with REAL pipeline data")
print("=" * 60)

# Load DB context exactly like pipeline does
db = Database('/Users/nghialam/jarvis-hub/knowledge/jarvis.db')
context_data = db.get_market_data()
articles = db.run_query("SELECT id, title, summary FROM news_articles ORDER BY id DESC LIMIT 10")

print(f"\nLoaded market data: {len(context_data.get('overview', []))} overview items")
print(f"Loaded articles: {len(articles)} articles")

# Build prompt (same as load_db_data in pipeline)
prompt = "Bạn là chuyên gia phân tích tài chính Việt Nam.\n\nMARKET DATA:\n"
prompt += json.dumps(context_data.get('overview', []), ensure_ascii=False, indent=2)
prompt += "\n\nARTICLES (" + str(len(articles)) + " items):\n"
for row in articles[:5]:
    prompt += "- " + (row[1] if row else 'empty') + " | Summary: " + str(row[2] or 'N/A') + "\n"

print(f"\nPrompt size: {len(prompt)} chars")
print("Sending to qwen3.6 with streaming...")

response = requests.post(
    'http://localhost:11434/api/chat',
    json={
        'model': 'qwen3.6:35b-a3b-mxfp8',
        'messages': [
            {'role': 'system', 'content': 'Vietnamese financial analyst. Reply in Vietnamese.'},
            {'role': 'user', 'content': prompt},
        ],
        'stream': True,
        'options': {'num_predict': 2048}
    },
    timeout=300,
    stream=True
)

print(f"\nHTTP status: {response.status_code}")

chunks_read = 0
extracted_chunks = []

for chunk_line in response.iter_lines():
    if not chunk_line.strip():
        continue
    chunks_read += 1
    
    try:
        chunk = json.loads(chunk_line)
        deltas = chunk.get('choices', [{}])
        delta = deltas[0].get('delta', {}).get('content', '') if deltas else ''
         
        done = chunk.get('done', False)
         
        if len(extracted_chunks) < 3 or chunks_read % 50 == 0:
            print(f"  Chunk {chunks_read}: delta_len={len(delta)} | done={done}")
         
        if delta:
            extracted_chunks.append(delta)
         
        if done and len(extracted_chunks) > 0:
            break
             
    except (json.JSONDecodeError, Exception) as e:
        import traceback
        print(f"ERROR chunk {chunks_read}: {e}")
        traceback.print_exc()

result = ''.join(extracted_chunks).strip()
print("\n=== FINAL RESULT ===")
print(f"Chunks extracted: {len(extracted_chunks)}")
print(f"Total chars: {len(result)}")
if result:
    print(f"\nPreview (first 500 chars):\n{result[:500]}...")
else:
    print("!!! NO CONTENT EXTRACTED - streaming parser FAILED !!!")
