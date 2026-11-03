import queue
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from engine import command, convert_batch


class EngineTest(unittest.TestCase):
    def test_explicit_hardware_encoders(self):
        for mode, codec in [("nvidia", "h264_nvenc"), ("amd", "h264_amf"), ("intel", "h264_qsv")]:
            args = command(Path("in.mov"), Path("out.mp4"), "1080", "30", True, mode, 1)
            self.assertEqual(args[args.index("-c:v") + 1], codec)
            self.assertNotIn("libx264", args)
            self.assertIn("-an", args)
            if mode == "nvidia":
                self.assertEqual(args[args.index("-gpu") + 1], "1")
        with self.assertRaises(ValueError):
            command(Path("in"), Path("out.webm"), "original", "original", False, "nvidia")

    def test_native_worker_preserves_sources_and_existing_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "sample.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=size=64x64:rate=10",
                    "-t",
                    "0.2",
                    "-c:v",
                    "libx264",
                    str(source),
                ],
                check=True,
            )
            original = source.read_bytes()
            existing = folder / "sample_converted.mp4"
            existing.write_bytes(b"keep this")
            events = queue.Queue()
            convert_batch(
                [source],
                folder,
                ("original", "30", True, "mp4", "cpu", 0),
                threading.Event(),
                events,
            )
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(existing.read_bytes(), b"keep this")
            self.assertGreater((folder / "sample_converted (1).mp4").stat().st_size, 100)
            self.assertFalse(list(folder.glob(".kadr-*")))
            events = list(events.queue)
            self.assertIn(("row", 0, "Готово"), events)

    def test_gpu_probe_uses_supported_frame_and_reports_driver_error(self):
        from types import SimpleNamespace

        from engine import probe_encoder

        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return SimpleNamespace(
                returncode=1, stderr=b"Driver does not support required NVENC API version"
            )

        reason = probe_encoder(Path("probe.mp4"), "nvidia", 0, runner=runner)
        self.assertIn("NVENC API", reason)
        self.assertIn("color=size=640x360:rate=30", calls[0])
        self.assertIn("-frames:v", calls[0])


class BatchFailureTest(unittest.TestCase):
    def test_invalid_file_does_not_stop_remaining_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            broken = folder / "broken.mp4"
            broken.write_bytes(b"not a video")
            valid = folder / "valid.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=size=64x64:rate=10",
                    "-t",
                    "0.2",
                    "-c:v",
                    "libx264",
                    str(valid),
                ],
                check=True,
            )
            events = queue.Queue()
            convert_batch(
                [broken, valid],
                folder,
                ("original", "original", False, "mp4", "cpu", 0),
                threading.Event(),
                events,
            )
            results = list(events.queue)
            self.assertTrue(
                any(e[0] == "row" and e[1] == 0 and e[2].startswith("Ошибка") for e in results)
            )
            self.assertIn(("row", 1, "Готово"), results)
            self.assertFalse((folder / "broken_converted.mp4").exists())
            self.assertFalse(list(folder.glob(".kadr-*")))
            self.assertEqual(broken.read_bytes(), b"not a video")

    def test_cancelled_batch_leaves_sources_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "source.mp4"
            source.write_bytes(b"source")
            cancel = threading.Event()
            cancel.set()
            events = queue.Queue()
            convert_batch(
                [source], folder, ("original", "original", False, "mp4", "cpu", 0), cancel, events
            )
            self.assertEqual(list(folder.iterdir()), [source])
            self.assertEqual(list(events.queue), [("finished",)])
