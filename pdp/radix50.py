import struct


TABLE = " ABCDEFGHIJKLMNOPQRSTUVWXYZ$.%0123456789"


def encode_char(char):
    return TABLE.index(char)


def encode_string(string):
    while len(string) % 3 != 0:
        string += " "
    result = b""
    for i in range(0, len(string), 3):
        a, b, c = string[i:i + 3]
        result += struct.pack("<H", encode_char(a) * 1600 + encode_char(b) * 40 + encode_char(c))
    return result
