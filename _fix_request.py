"""Fix the requests.post() call in jarvis_app.py by adding json={ wrapper."""
with open('jarvis_app.py') as f:
    lines = f.readlines()

# Find line 1223: "        r = requests.post("
# Need to change to: "        r = requests.post(
#                                   json={"
# Line 1225 currently starts with: '              "%s/v1/chat...%'
# It needs to be indented more to align under json={

print(f"Lines count before: {len(lines)}")

# Line 1223: change "requests.post(" to "requests.post("
# Then insert a new line after it with "json={"

# Strategy: 
# Replace the URL argument line (1225) and add json keyword before all dict keys
# Actually, better approach: insert 'json={' at position 1224 (after requests.post() call starts)

# Line 1223 is index 1222 in 0-indexed
# Current line 1225 (index 1224): '              "%s/v1/chat/completions" % ollama_url,'
# This needs to become: json={\n              "model": model,\n              ...

# Let me find the exact line to insert after
insert_after_idx = None  # line index (0-based) where we'll insert json={
for i in range(1220, 1230):
    if 'requests.post' in lines[i]:
        insert_after_idx = i
        print(f"Found requests.post at line {i+1} (index {i})")

if insert_after_idx is None:
    print("ERROR: Could not find requests.post line")
    exit(1)

# Count leading spaces on the URL line (line 1225, index 1224)
url_line = lines[insert_after_idx + 1]
spaces = len(url_line) - len(url_line.lstrip())
indent = ' ' * spaces
print(f"URL line indent: {spaces} spaces")

# New line to insert after requests.post(
json_wrapper = indent + 'json={\n'
lines.insert(insert_after_idx + 1, json_wrapper)

# Now re-indent all dict keys (model, messages, stream, options) to match under json={
for i in range(len(lines)):
    line = lines[i].rstrip('\n')
    stripped = line.strip()
    
    # Skip blank lines and the closing brace/timeout/closing paren
    if not stripped:
        continue
        
    # The dict keys we need to indent more (model, messages, stream, options)
    if stripped.startswith('"model"') or stripped.startswith('"messages"'):
        # Line was 16 spaces, needs 20 (add 4 for json={)
        orig_spaces = len(line) - len(line.lstrip())
        new_indent = ' ' * (orig_spaces + 4)
        lines[i] = new_indent + stripped + '\n'
        print(f"Line {i+1}: indented from {orig_spaces} to {len(new_indent)}")
    elif stripped.startswith('"stream"'):
        orig_spaces = len(line) - len(line.lstrip())
        new_indent = ' ' * (orig_spaces + 4)
        lines[i] = new_indent + stripped + '\n'
        print(f"Line {i+1}: indented from {orig_spaces} to {len(new_indent)}")
    elif stripped.startswith('"options"'):
        orig_spaces = len(line) - len(line.lstrip())
        new_indent = ' ' * (orig_spaces + 4)
        lines[i] = new_indent + stripped + '\n'
        print(f"Line {i+1}: indented from {orig_spaces} to {len(new_indent)}")
    elif stripped.startswith('num_predict') or stripped.startswith('temperature'):
        orig_spaces = len(line) - len(line.lstrip())
        new_indent = ' ' * (orig_spaces + 4)
        lines[i] = new_indent + stripped + '\n'
        print(f"Line {i+1}: indented from {orig_spaces} to {len(new_indent)}")

# Fix closing braces - they now need extra 4 spaces too
for i in range(len(lines)):
    stripped = lines[i].strip()
    if stripped == '},' or stripped == '},': 
        orig_spaces = len(lines[i]) - len(lines[i].lstrip())
        new_ind = ' ' * (orig_spaces + 4)
        lines[i] = new_ind + '},\n'
    elif stripped == '}':
        orig_spaces = len(lines[i]) - len(lines[i].lstrip())
        new_ind = ' ' * (orig_spaces + 4)
        lines[i] = new_ind + '}\n'

# The closing paren on line 1251 is NOT part of the json dict, so it stays at same indent
final_indent_corrected = 0
for i in range(len(lines)):
    stripped = lines[i].strip()
    if stripped == ')':
        final_indent_corrected += 1

print(f"Lines count after: {len(lines)}")
print(f"Indent corrected for closing paren")

# Write the modified file
with open('jarvis_app.py', 'w') as f:
    f.writelines(lines)

print("Done! File patched.")
