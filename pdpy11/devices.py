import collections
import contextlib
import io
import os
import re
import subprocess
import sys
import time
import tempfile


DEVICES = collections.defaultdict(dict)


def register_device(name, mode, input_formats=None):
    assert name.startswith("~")
    assert name[1:].isalpha()
    assert name[1:].lower() == name[1:]
    # assert mode in ("rb", "wb")
    assert mode == "wb"  # for now

    def decorator(fn):
        DEVICES[name[1:]][mode] = (input_formats, fn)

    return decorator


class WriteDeviceHandler:
    def __init__(self, handler_fn):
        self.handler_fn = handler_fn
        self.data = io.BytesIO()
        self.closed = False

    def write(self, data: bytes):
        self.data.write(data)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.close()

    def close(self):
        if not self.closed:
            self.closed = True
            self.handler_fn(self.data.getvalue())


@contextlib.contextmanager
def materialize_file(data: bytes, suffix: str=None):
    try:
        f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        f.write(data)
        f.close()
        yield f.name
    finally:
        os.unlink(f.name)


@register_device("~speaker", "wb", input_formats=["wav"])
def speaker(audio_data):
    # pragma: no cover

    if os.name == "nt":
        # On Windows, we use a built-in module
        print("Playing wave audio via winsound")
        import winsound
        with materialize_file(audio_data, ".wav") as file_name:
            winsound.PlaySound(file_name, winsound.SND_MEMORY)
        return

    if sys.platform == "darwin":
        # On macOS, the built-in Python distribution has AppKit module
        try:
            import AppKit
        except ImportError:
            pass
        else:
            print("Playing wave audio via AppKit")
            with materialize_file(audio_data, ".wav") as file_name:
                sound = AppKit.NSSound.alloc()
                sound.initWithContentsOfFile_byReference_(file_name, True)
                sound.play()
                time.sleep(sound.duration())
            return

        # On macOS, there's afplay command which we use as a fallback
        with materialize_file(audio_data, ".wav") as file_name:
            print("Playing wave audio via afplay")
            subprocess.run(["afplay", "-q", "1", file_name])
        return

    # On Linux with GTK, we use 'gi' module
    try:
        import gi
    except ImportError:
        pass
    else:
        print("Playing wave audio via GTK playbin")

        import urllib.request
        gi.require_version("Gst", "1.0")

        from gi.repository import Gst
        Gst.init(None)

        playbin = Gst.ElementFactory.make("playbin", "pdpy11")
        with materialize_file(audio_data, ".wav") as file_name:
            playbin.set_property("uri", "file://" + urllib.request.pathname2url(file_name))
        playbin.set_state(Gst.State.PLAYING)
        playbin.get_bus().poll(Gst.MessageType.EOS, Gst.CLOCK_TIME_NONE)
        playbin.set_state(Gst.State.NULL)

        return

    # On Linux with OSS and Cygwin we use ossaudiodev
    try:
        os.stat("/dev/dsp")
    except FileNotFoundError:
        pass
    else:
        print("Playing wave audio via OSS")

        import wave
        import ossaudiodev

        with io.BytesIO(audio_data) as f_wav:
            with wave.open(f_wav, "rb") as audio_wav:
                nchannels = audio_wav.getnchannels()
                framerate = audio_wav.getframerate()
                nframes = audio_wav.getnframes()
                raw_audio_data = audio_wav.readframes(nframes)

        with ossaudiodev.open("/dev/dsp", "w") as dsp:
            dsp.setparameters(ossaudiodev.AFMT_U8, nchannels, framerate)
            dsp.write(raw_audio_data)

        return

    # On Linux with ALSA we use aplay
    try:
        subprocess.run(["aplay", "--version"])
    except FileNotFoundError:
        pass
    else:
        print("Playing wave audio via ALSA")
        subprocess.run(["aplay", "-"], input=audio_data)
        return

    # On Linux with PulseAudio we use paplay
    try:
        subprocess.run(["paplay", "--version"], input=audio_data)
    except FileNotFoundError:
        pass
    else:
        print("Playing wave audio via PulseAudio")
        with materialize_file(audio_data, ".wav") as file_name:
            subprocess.run(["paplay", file_name])
        return

    # On Linux and Cygwin with SOX we use it
    try:
        subprocess.run(["sox", "--version"], input=audio_data)
    except FileNotFoundError:
        pass
    else:
        print("Playing wave audio via SOX")
        with materialize_file(audio_data, ".wav") as file_name:
            subprocess.run(["sox", file_name, "-d"])
        return

    # If ffplay is available, we use it
    try:
        subprocess.run(["ffplay", "--version"])
    except FileNotFoundError:
        pass
    else:
        print("Playing wave audio via ffmpeg")
        with materialize_file(audio_data, ".wav") as file_name:
            subprocess.run(["ffplay", file_name])
        return

    # Otherwise use xdg-open to open the default program for WAWs on this system
    try:
        subprocess.run(["xdg-open", "--version"])
    except FileNotFoundError:
        pass
    else:
        print("Playing wave audio via xdg-open")
        with materialize_file(audio_data, ".wav") as file_name:
            subprocess.run(["xdg-open", file_name])
        return

    print("Speaker output is not supported on your system.")


def is_device_path(path: str):
    match = re.match(r"^~([a-z]+)($| )", path, flags=re.I)
    return match is not None and match[1].lower() in DEVICES


def is_absolute_path(path: str):
    return path == os.path.abspath(path) or is_device_path(path)


def open_device(path, mode="rb", data_format=None):
    """
    Open a device like open() but supporting specific devices like ~speaker.

    A device name starts with a tilde and is followed by a short alphabetical
    name, e.g. '~speaker'.
    """

    if not is_device_path(path):
        return open(path, mode)

    name = path[1:].split()[0]

    dev = DEVICES[name]
    if mode not in dev:
        raise IOError(f"Device ~{name} does not support {mode} mode")

    dev_formats, dev_fn = dev[mode]
    if data_format is not None and dev_formats is not None and data_format not in dev_formats:
        raise IOError(f"Device ~{name} only works with any of {dev_formats} formats in {mode} mode. Mode {data_format} is unsupported.")

    assert mode == "wb"
    return WriteDeviceHandler(dev_fn)


def resolve_relative_path(relative_path: str, base_file_path: str):
    if is_absolute_path(relative_path):
        return relative_path
    else:
        return os.path.normpath(os.path.join(os.path.dirname(base_file_path), relative_path))
