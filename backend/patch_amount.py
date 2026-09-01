import re

path = 'tests/api/test_metrics_dashboard_regression.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

new_content = re.sub(r'amount=[\'\"]100\.00[\'\"]', 'amount=10000', content)
new_content = re.sub(r'amount=[\'\"]200\.00[\'\"]', 'amount=20000', new_content)
new_content = re.sub(r'amount=[\'\"]300\.00[\'\"]', 'amount=30000', new_content)

if new_content != content:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Patched amounts')
