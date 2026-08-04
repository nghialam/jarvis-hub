#!/usr/bin/env python3
"""Hotfix for jarvis_app.py - fix requests.post() syntax error"""

import re

filepath = "/Users/nghialam/jarvis-hub/jarvis_app.py"

with open(filepath, 'r') as f:
    content = f.read()

# Pattern to find the broken requests.post block
# The block starts with "r = requests.post(" and ends with "timeout=120,\n         )"
old_pattern = r'''        r = requests\.post\(
            
              "%s/v1/chat/completions" % ollama_url,
                "model": model,
                
                "messages": \[
                    
                    \{"role": "system", "content": "Ban la chuyen gia phan tich thi truong tai chinh Viet Nam\. Tra loi bang tieng Viet\."\},
                    
                    \{"role": "user", "content": prompt % context_text\},
                    
                \],
                
                "stream": False,
                
                "options": \{
                    
                    "num_predict": 4096,
                    
                    "temperature": 0.7,
                    
                \},
                
            \},
            
            timeout=120,
            
         \)'''

new_pattern = '''        r = requests.post(
              "%s/v1/chat/completions" % ollama_url,
             json={
                 "model": model,
                 "messages": [
                     {"role": "system", "content": "Ban la chuyen gia phan tich thi truong tai chinh Viet Nam. Tra loi bang tieng Viet."},
                     {"role": "user", "content": prompt % context_text},
                 ],
                 "stream": False,
                 "options": {
                     "num_predict": 4096,
                     "temperature": 0.7,
                 },
             },
            timeout=120,
         )'''

if re.search(old_pattern, content):
    content = re.sub(old_pattern, new_pattern, content)
    print("Pattern matched and replaced via regex")
else:
    # Fallback: line-by-line replacement
    lines = content.split('\n')
    
    # Find the request.post block by searching for the URL line
    url_line_idx = None
    for i, line in enumerate(lines):
        if '"%s/v1/chat/completions" % ollama_url' in line:
            url_line_idx = i
            break
    
    if url_line_idx is not None:
        # Replace from url_line_idx to closing ) - preserve structure
        # Lines around 1225-1251
        new_lines = [
            '              "%s/v1/chat/completions" % ollama_url,',
            '             json={',
            '                 "model": model,',
            '                 "messages": [',
            '                     {"role": "system", "content": "Ban la chuyen gia phan tich thi truong tai chinh Viet Nam. Tra loi bang tieng Viet."},',
            '                     {"role": "user", "content": prompt % context_text},',
            '                 ],',
            '                 "stream": False,',
            '                 "options": {',
            '                     "num_predict": 4096,',
            '                     "temperature": 0.7,',
            '                 },',
            '             },',
            '            timeout=120,',
            '         )',
        ]
        
        # Find end marker: line containing ") that starts with spaces after timeout
        end_idx = None
        for i in range(url_line_idx, min(url_line_idx + 50, len(lines))):
            stripped = lines[i].strip()
            if (stripped == ')' and 
                i > url_line_idx + 10 and  # should be at least 10+ lines after
                ('timeout' in '\n'.join(lines[url_line_idx:i]) or 
                 'stream' in '\n'.join(lines[url_line_idx:i]))):
                end_idx = i
                break
        
        if end_idx is not None:
            # Replace the block preserving surrounding blank lines
            before_blank = ''
            after_blank = ''
            if url_line_idx > 0 and lines[url_line_idx-1].strip() == '':
                before_blank = '\n'
            if end_idx + 1 < len(lines) and lines[end_idx+1].strip() == '':
                after_blank = '\n'
            
            lines[url_line_idx:end_idx+1] = [before_blank + new_line for new_line in new_lines] + [after_blank]
            content = '\n'.join(lines)
            print(f"Fixed via line replacement (url@{url_line_idx+1} to {end_idx+1})")
        else:
            print("ERROR: Could not find end of requests.post block")
    else:
        print("ERROR: Could not find URL line")

with open(filepath, 'w') as f:
    f.write(content)

print("Done. Verifying syntax...")
import py_compile
try:
    py_compile.compile(filepath, doraise=True)
    print("Syntax OK!")
except py_compile.PyCompileError as e:
    print(f"Syntax ERROR: {e}")
