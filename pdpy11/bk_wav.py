import struct


def translate_audio_levels(string):
    return bytes({"H": 208, "S": 200, "L": 48}[char] for char in string)


class Env:
    ONE = translate_audio_levels("SSLLHHHHLLLL")
    ZERO = translate_audio_levels("SSLLHHLL")
    SYNC_MID = translate_audio_levels("SSSSSSSSLLLLLLLLHHHHLLLL")
    PAUSE = translate_audio_levels("SSLL") * 10 + SYNC_MID
    SYNC = translate_audio_levels("SSLL") * 4096 + SYNC_MID + PAUSE
    EOF = translate_audio_levels("SSLL") * 200
    sample_rate = 21428


class TurboEnv:
    ONE = translate_audio_levels("HHHLL")
    ZERO = translate_audio_levels("HLL")
    SYNC = translate_audio_levels("SSSLLL") * 1024 + translate_audio_levels("SSSSSSSSSSSSLLLLLLLLLLLL")
    PAUSE = translate_audio_levels("LLLL")
    EOF = translate_audio_levels("SSSLLLSSSLLL")
    sample_rate = 40000


def encode_as_wav(base, code, bk_filename, turbo=False):
    env = TurboEnv if turbo else Env
    return make_wav_file(
        (
            env.SYNC
            + encode_data_bits(struct.pack("<HH16s", base, len(code), bk_filename), env)
            + env.PAUSE
            + encode_data_bits(code, env)
            + (env.PAUSE if turbo else b"")
            + encode_data_bits(struct.pack("<H", sum(code) % (2 ** 16 - 1)), env)
            + env.EOF
        ),
        env.sample_rate
    )


def encode_data_bits(data, env):
    return b"".join([env.ZERO, env.ONE][(byte >> i) & 1] for byte in data for i in range(8))


def make_wav_file(data, sample_rate):
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,  # sub chunk 1 size (always 16)
        1,  # PCM format
        1,  # channel count
        sample_rate,  # sample rate in samples
        sample_rate,  # sample rate in bytes
        1,  # block alignment
        8,  # sound depth (8 bits)
        b"data",
        len(data)  # size of the first subchunk
    ) + data
