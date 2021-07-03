import struct


TABLE = " ABCDEFGHIJKLMNOPQRSTUVWXYZ$.%0123456789"


def encode_char(char):
    return TABLE.index(char)


def pack_to_int(string):
    assert len(string) <= 3
    string = string.ljust(3, " ")
    a, b, c = string
    return encode_char(a) * 1600 + encode_char(b) * 40 + encode_char(c)


def encode_string(string):
    result = b""
    for i in range(0, len(string), 3):
        result += struct.pack("<H", pack_to_int(string[i:i + 3]))
    return result
