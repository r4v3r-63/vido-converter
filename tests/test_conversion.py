import json
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import app


class ConversionTest(unittest.TestCase):
    def test_formats_dimensions_fps_and_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.mov'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=15', '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '0.4', '-c:v', 'libx264', '-c:a', 'aac', str(source)], check=True)
            for fmt in app.FORMATS:
                for mute in (False, True):
                    with self.subTest(format=fmt, mute=mute):
                        target = root / f'out-{mute}.{fmt}'
                        subprocess.run(app.command(source, target, '480', '30', mute), check=True, capture_output=True)
                        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(target)]))
                        video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
                        self.assertEqual((video['width'], video['height']), (854, 480))
                        self.assertEqual(video['r_frame_rate'], '30/1')
                        self.assertEqual(any(s['codec_type'] == 'audio' for s in probe['streams']), not mute)

    def test_http_batch_download_and_invalid_file(self):
        import threading
        import zipfile
        import io
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            self.assertIn('Кадр', urllib.request.urlopen(base).read().decode())
            with tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / 'test.mp4'
                subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=64x64:rate=10', '-t', '0.2', '-c:v', 'libx264', str(source)], check=True)
                boundary = 'test-boundary-123'
                body = b''
                for name, data in [('test.mp4', source.read_bytes()), ('broken.avi', b'not a video')]:
                    body += f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + data + b'\r\n'
                body += f'--{boundary}--\r\n'.encode()
                request = urllib.request.Request(base + '/convert', data=body, headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
                job_id = json.load(urllib.request.urlopen(request))['id']
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    job = json.load(urllib.request.urlopen(base + '/jobs/' + job_id))
                    if job['status'] == 'done':
                        break
                    time.sleep(0.1)
                self.assertEqual(job['status'], 'done')
                self.assertEqual([f['status'] for f in job['files']], ['done', 'error'])
                self.assertGreater(len(urllib.request.urlopen(base + job['files'][0]['url']).read()), 100)
                archive = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(base + job['archive']).read()))
                self.assertEqual(archive.namelist(), ['001_test.mp4'])
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(base + '/download/' + job_id + '/input_0')
                self.assertEqual(denied.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            for job in list(app.JOBS.values()):
                app.shutil.rmtree(job['directory'], ignore_errors=True)
            app.JOBS.clear()


if __name__ == '__main__':
    unittest.main()
