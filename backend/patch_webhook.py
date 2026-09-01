import re
import os

filepath = 'tests/security/test_batch531_webhook_retry.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

new_lines = []
for line in content.split('\n'):
    match = re.search(r'transaction_id=[\'\"]([^\'\"]+)[\'\"]', line)
    if match and 'WebhookEvent' not in line and 'RecoveryAttempt' not in line and 'event =' not in line and 'assert' not in line and 'def ' not in line and 'query' not in line:
        txn_id = match.group(1)
        indent = line[:len(line) - len(line.lstrip())]
        if 'Transaction(id' not in ''.join(new_lines[-5:]):
            new_lines.append(f'{indent}db_session.add(Transaction(id="{txn_id}", amount=100))')
            new_lines.append(f'{indent}db_session.flush()')
    new_lines.append(line)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))
print(f'Patched {filepath}')
