"""FFmpeg commands, hardware probing and batch processing without GUI dependencies."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
BUNDLED = getattr(sys, "frozen", False)
FFMPEG = str(ROOT / "ffmpeg.exe") if BUNDLED else "ffmpeg"
SIZES = {
    "original": None,
    "2160": (3840, 2160),
    "1080": (1920, 1080),
    "720": (1280, 720),
    "480": (854, 480),
}
FORMATS = {
    "mp4": [
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
    ],
    "mkv": ["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "aac"],
    "webm": ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-c:a", "libopus"],
}


def command(source, target, size, fps, mute, encoder="cpu", device=0):
    filters = []
    if SIZES[size]:
        w, h = SIZES[size]
        filters.append(
            f"scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )
    else:
        filters.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
    if fps != "original":
        filters.append(f"fps={fps}")
    args = [
        FFMPEG,
        "-nostdin",
        "-y",
        "-v",
        "error",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-vf",
        ",".join(filters),
        *FORMATS[target.suffix[1:]],
        "-pix_fmt",
        "yuv420p",
        "-threads",
        "2",
    ]
    if encoder != "cpu":
        if target.suffix == ".webm":
            raise ValueError(
                "Для аппаратного кодирования выберите MP4 или MKV. WebM доступен на процессоре."
            )
        options = {
            "nvidia": [
                "-c:v",
                "h264_nvenc",
                "-gpu",
                str(device),
                "-preset",
                "p4",
                "-cq",
                "23",
                "-b:v",
                "0",
            ],
            "amd": ["-c:v", "h264_amf", "-quality", "balanced", "-qp_i", "23", "-qp_p", "23"],
            "intel": ["-c:v", "h264_qsv", "-global_quality", "23"],
        }
        if encoder not in options:
            raise ValueError("Неизвестный аппаратный кодировщик")
        start = args.index("-c:v")
        end = args.index("-c:a", start)
        args[start:end] = options[encoder]
    if mute:
        args.append("-an")
    return args + [str(target)]


def probe_encoder(target, encoder, device, runner=subprocess.run):
    """Use a normal frame size: hardware encoders can reject tiny images."""
    args = command(Path("unused"), target, "original", "original", True, encoder, device)
    index = args.index("-i")
    args[index : index + 2] = ["-f", "lavfi", "-i", "color=size=640x360:rate=30", "-frames:v", "3"]
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    result = runner(args, capture_output=True, timeout=30, **flags)
    return (
        None
        if result.returncode == 0
        else result.stderr.decode("utf-8", "replace").strip() or "FFmpeg вернул ошибку без описания"
    )


def convert_batch(paths, destination, settings, cancel, events):
    size, fps, mute, fmt, encoder, device = settings
    for index, source in enumerate(paths):
        if cancel.is_set():
            break
        events.put(("row", index, "Обработка…"))
        target = temporary = None
        try:
            # Exclusive reservation protects originals and existing results,
            # including identical filenames from different source folders.
            number = 0
            while True:
                suffix = "" if number == 0 else f" ({number})"
                target = destination / f"{source.stem}_converted{suffix}.{fmt}"
                try:
                    target.open("xb").close()
                    break
                except FileExistsError:
                    number += 1
            fd, name = tempfile.mkstemp(suffix="." + fmt, prefix=".kadr-", dir=destination)
            os.close(fd)
            temporary = Path(name)
            with tempfile.TemporaryFile() as errors:
                process = subprocess.Popen(
                    command(source, temporary, size, fps, mute, encoder, device),
                    stdout=subprocess.DEVNULL,
                    stderr=errors,
                    **(
                        {"creationflags": subprocess.CREATE_NO_WINDOW}
                        if sys.platform == "win32"
                        else {}
                    ),
                )
                while process.poll() is None:
                    if cancel.wait(0.1):
                        process.terminate()
                        process.wait()
                        break
                if cancel.is_set():
                    raise InterruptedError("Остановлено")
                if process.returncode:
                    errors.seek(0)
                    raise ValueError(
                        errors.read().decode("utf-8", "replace")[-2000:] or "Ошибка FFmpeg"
                    )
            os.replace(temporary, target)
            temporary = None
            target = None
            events.put(("row", index, "Готово"))
        except Exception as exc:
            events.put(("row", index, "Остановлено" if cancel.is_set() else "Ошибка: " + str(exc)))
        finally:
            for path in (temporary, target):
                if path is not None:
                    path.unlink(missing_ok=True)
        events.put(("progress", index + 1))
    events.put(("finished",))
