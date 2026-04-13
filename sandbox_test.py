import subprocess
import tempfile
import os

code = """
import subprocess
try:
    subprocess.Popen(['notepad.exe'])
    print('Notepad launched')
except Exception as e:
    print('Error:', e)
"""

with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
    f.write(code)
    test_file = f.name

print(f"Testing with capture_output=True...")
result = subprocess.run(['python', test_file], capture_output=True, text=True)
print("STDOUT:", result.stdout.strip())
print("STDERR:", result.stderr.strip())

os.remove(test_file)
