import io
import tempfile
import unittest
from pathlib import Path

from app import read_upload


class UploadTest(unittest.TestCase):
    def test_more_than_100_files_and_split_boundaries(self):
        class Chunked(io.BytesIO):
            def read(self, size=-1):
                return super().read(min(size, 7))
        body = b''.join(b'--batch\r\nContent-Disposition: form-data; name="files"; filename="clip.mp4"\r\n\r\nvideo\r\n' for _ in range(101)) + b'--batch--\r\n'
        with tempfile.TemporaryDirectory() as tmp:
            fields, files = read_upload(Chunked(body), len(body), 'multipart/form-data; boundary=batch', Path(tmp))
            self.assertEqual(len(files), 101)
            self.assertTrue(all(path.read_bytes() == b'video' for path, name in files))

    def test_upload_over_512mb_uses_bounded_reads(self):
        prefix = b'--large\r\nContent-Disposition: form-data; name="files"; filename="large.mp4"\r\n\r\n'
        suffix = b'\r\n--large--\r\n'
        size = 513 * 1024 * 1024
        class Generated:
            position = 0
            def read(self, count):
                if count > 1024 * 1024:
                    raise AssertionError('Upload read is unbounded')
                start = self.position
                end = min(start + count, len(prefix) + size + len(suffix))
                self.position = end
                result = prefix[start:min(end, len(prefix))] if start < len(prefix) else b''
                result += b'x' * max(0, min(end, len(prefix) + size) - max(start, len(prefix)))
                if end > len(prefix) + size:
                    result += suffix[max(0, start - len(prefix) - size):end - len(prefix) - size]
                return result
        with tempfile.TemporaryDirectory() as tmp:
            _, files = read_upload(Generated(), len(prefix) + size + len(suffix), 'multipart/form-data; boundary=large', Path(tmp))
            self.assertEqual(files[0][0].stat().st_size, size)

    def test_truncated_upload_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                read_upload(io.BytesIO(b'--broken\r\n'), 500, 'multipart/form-data; boundary=broken', Path(tmp))
