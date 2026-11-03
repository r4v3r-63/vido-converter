import queue
import tempfile
import threading
import unittest
from pathlib import Path
import subprocess

from app import command
from desktop import Converter


class DesktopTest(unittest.TestCase):
    def test_explicit_hardware_encoders(self):
        for mode, codec in [('nvidia', 'h264_nvenc'), ('amd', 'h264_amf'), ('intel', 'h264_qsv')]:
            args = command(Path('in.mov'), Path('out.mp4'), '1080', '30', True, mode, 1)
            self.assertEqual(args[args.index('-c:v') + 1], codec)
            self.assertNotIn('libx264', args)
            self.assertIn('-an', args)
            if mode == 'nvidia':
                self.assertEqual(args[args.index('-gpu') + 1], '1')
        with self.assertRaises(ValueError):
            command(Path('in'), Path('out.webm'), 'original', 'original', False, 'nvidia')

    def test_native_worker_preserves_sources_and_existing_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / 'sample.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=64x64:rate=10', '-t', '0.2', '-c:v', 'libx264', str(source)], check=True)
            original = source.read_bytes()
            existing = folder / 'sample_converted.mp4'
            existing.write_bytes(b'keep this')
            ui = Converter.__new__(Converter)
            ui.cancel = threading.Event()
            ui.events = queue.Queue()
            ui.work([source], folder, ('original', '30', True, 'mp4', 'cpu', 0))
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(existing.read_bytes(), b'keep this')
            self.assertGreater((folder / 'sample_converted (1).mp4').stat().st_size, 100)
            self.assertFalse(list(folder.glob('.kadr-*')))
            events = list(ui.events.queue)
            self.assertIn(('row', 0, 'Готово'), events)
