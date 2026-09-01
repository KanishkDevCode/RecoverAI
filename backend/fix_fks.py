import re
import os
import glob

def patch_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    new_lines = []
    lines = content.split('\n')
    modified = False
    
    for line in lines:
        match_webhook = re.search(r'WebhookEvent\([^)]*transaction_id=[\'\"]([^\'\"]+)[\'\"]', line)
        if match_webhook and 'Transaction(id' not in ''.join(new_lines[-5:]):
            txn_id = match_webhook.group(1)
            indent = line[:len(line) - len(line.lstrip())]
            new_lines.append(f'{indent}db.add(Transaction(id="{txn_id}", amount=100))')
            new_lines.append(f'{indent}db.flush()')
            modified = True
            
        match_attempt = re.search(r'RecoveryAttempt\([^)]*transaction_id=[\'\"]([^\'\"]+)[\'\"]', line)
        if match_attempt and 'Transaction(id' not in ''.join(new_lines[-5:]):
            txn_id = match_attempt.group(1)
            indent = line[:len(line) - len(line.lstrip())]
            new_lines.append(f'{indent}db.add(Transaction(id="{txn_id}", amount=100))')
            new_lines.append(f'{indent}db.flush()')
            modified = True

        new_lines.append(line)

    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        print(f"Patched FKs in {filepath}")

for root, _, files in os.walk('tests'):
    for f in files:
        if f.endswith('.py'):
            patch_file(os.path.join(root, f))
