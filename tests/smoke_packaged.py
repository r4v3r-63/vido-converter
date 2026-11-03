"""Exercise the packaged exe, including its embedded FFmpeg, on the build runner."""
import io
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
import traceback
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / 'sample.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=64x64:rate=10', '-t', '0.2', '-c:v', 'libx264', str(source)], check=True)
        log = root / 'server.log'
        with log.open('w') as stream:
            process = subprocess.Popen([str(Path(sys.argv[1]).resolve()), '--port', '0', '--no-browser'], stdout=stream, stderr=stream)
            try:
                address = None
                for _ in range(120):
                    text = log.read_text(errors='replace')
                    if 'http://127.0.0.1:' in text:
                        address = 'http://127.0.0.1:' + text.split('http://127.0.0.1:', 1)[1].split()[0]
                        break
                    if process.poll() is not None:
                        raise RuntimeError(text)
                    time.sleep(1)
                if not address:
                    raise RuntimeError('Application did not start')
                assert 'Кадр' in urllib.request.urlopen(address).read().decode()
                body = b'--smoke\r\nContent-Disposition: form-data; name="files"; filename="sample.mp4"\r\nContent-Type: video/mp4\r\n\r\n' + source.read_bytes() + b'\r\n--smoke--\r\n'
                req = urllib.request.Request(address + '/convert', data=body, headers={'Content-Type': 'multipart/form-data; boundary=smoke'})
                job_id = json.load(urllib.request.urlopen(req))['id']
                for _ in range(60):
                    job = json.load(urllib.request.urlopen(address + '/jobs/' + job_id))
                    if job['status'] == 'done':
                        break
                    time.sleep(1)
                assert job['status'] == 'done', job
                assert job['files'][0]['status'] == 'done', job
                data = urllib.request.urlopen(address + job['archive']).read()
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    assert archive.namelist() == ['001_sample.mp4']
                print('Packaged executable: upload, bundled FFmpeg conversion and ZIP download passed')
            except Exception:
                detail = traceback.format_exc() + '\nServer output:\n' + log.read_text(errors='replace')
                print('::error::' + detail.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A'))
                raise
            finally:
                if sys.platform == 'win32':
                    # One-file PyInstaller starts a child process; stop the whole
                    # tree so Windows releases inherited log handles before cleanup.
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    process.terminate()
                process.wait(timeout=20)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        detail = traceback.format_exc().encode('ascii', 'backslashreplace').decode()
        print('::error::' + detail.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A'), flush=True)
        raise
