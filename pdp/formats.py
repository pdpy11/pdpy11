import struct


file_formats = {}


def file_format(fn):
    name = fn.__name__.rstrip("_")
    file_formats[name] = fn


@file_format
def bin_(base, code):
    return struct.pack("<HH", base, len(code)) + code


@file_format
def raw(base, code):
    return code
