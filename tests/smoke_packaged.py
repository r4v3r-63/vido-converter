"""Verify the real native window and bundled conversion engine on Windows."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmp:
    report = Path(tmp) / 'report.json'
    process = subprocess.Popen([str(Path(sys.argv[1]).resolve()), '--smoke-test', str(report)])
    try:
        process.wait(timeout=120)
        if not report.exists():
            raise RuntimeError('Desktop application failed to produce GUI test report')
        result = json.loads(report.read_text(encoding='utf-8'))
        if not result.get('success'):
            raise RuntimeError(str(result))
        print('Native window, file selection, conversion and direct output: passed')
    except Exception as exc:
        print('::error::' + str(exc).encode('ascii', 'backslashreplace').decode())
        raise
    finally:
        if process.poll() is None:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
            process.wait(timeout=20)
