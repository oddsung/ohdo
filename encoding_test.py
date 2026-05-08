import os
import subprocess
import tempfile

code = """
print('한글 테스트 중입니다...')
"""

with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
    f.write(code)
    test_file = f.name

print("1. Without env:")
result1 = subprocess.run(['python', '-u', test_file], capture_output=True, text=True, encoding='utf-8', errors='replace')
print("STDOUT:", repr(result1.stdout))

print("2. With PYTHONIOENCODING=utf-8:")
env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'
result2 = subprocess.run(['python', '-u', test_file], capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)
print("STDOUT:", repr(result2.stdout))

os.remove(test_file)
