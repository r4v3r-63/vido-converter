import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import engine


class ConversionTest(unittest.TestCase):
    def test_formats_dimensions_fps_and_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mov"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=320x240:rate=15",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440",
                    "-t",
                    "0.4",
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    str(source),
                ],
                check=True,
            )
            for fmt in engine.FORMATS:
                for mute in (False, True):
                    with self.subTest(format=fmt, mute=mute):
                        target = root / f"out-{mute}.{fmt}"
                        subprocess.run(
                            engine.command(source, target, "480", "30", mute),
                            check=True,
                            capture_output=True,
                        )
                        probe = json.loads(
                            subprocess.check_output(
                                [
                                    "ffprobe",
                                    "-v",
                                    "error",
                                    "-show_streams",
                                    "-of",
                                    "json",
                                    str(target),
                                ]
                            )
                        )
                        video = next(s for s in probe["streams"] if s["codec_type"] == "video")
                        self.assertEqual((video["width"], video["height"]), (854, 480))
                        self.assertEqual(video["r_frame_rate"], "30/1")
                        self.assertEqual(
                            any(s["codec_type"] == "audio" for s in probe["streams"]), not mute
                        )


if __name__ == "__main__":
    unittest.main()
