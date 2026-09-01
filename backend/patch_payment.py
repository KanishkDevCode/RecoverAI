import re

path = 'tests/api/test_metrics_dashboard_regression.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

new_content = re.sub(r', payment_method=[\'"]card[\'"]', '', content)

if new_content != content:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Patched payment_method')
