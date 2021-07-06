import codecs


DECODING_TABLE = [
    "\x00", "\x01", "\x02", "\x03", "\x04", "\x05", "\x06", "\x07",
    "\x08", "\x09", "\x0a", "\x0b", "\x0c", "\x0d", "\x0e", "\x0f",
    "\x10", "\x11", "\x12", "\x13", "\x14", "\x15", "\x16", "\x17",
    "\x18", "\x19", "\x1a", "\x1b", "\x1c", "\x1d", "\x1e", "\x1f",
    " "   , "!"   , "\""  , "#"   , "$¤"  , "%"   , "&"   , "'"   ,
    "("   , ")"   , "*"   , "+"   , ","   , "-"   , "."   , "/"   ,
    "0"   , "1"   , "2"   , "3"   , "4"   , "5"   , "6"   , "7"   ,
    "8"   , "9"   , ":"   , ";"   , "<"   , "="   , ">"   , "?"   ,
    "@"   , "A"   , "B"   , "C"   , "D"   , "E"   , "F"   , "G"   ,
    "H"   , "I"   , "J"   , "K"   , "L"   , "M"   , "N"   , "O"   ,
    "P"   , "Q"   , "R"   , "S"   , "T"   , "U"   , "V"   , "W"   ,
    "X"   , "Y"   , "Z"   , "["   , "\\"  , "]"   , "^"   , "_"   ,
    "`"   , "a"   , "b"   , "c"   , "d"   , "e"   , "f"   , "g"   ,
    "h"   , "i"   , "j"   , "k"   , "l"   , "m"   , "n"   , "o"   ,
    "p"   , "q"   , "r"   , "s"   , "t"   , "u"   , "v"   , "w"   ,
    "x"   , "y"   , "z"   , "{"   , "|"   , "}"   , "~"   , "■"   ,
    "\x80", "\x81", "\x82", "\x83", "\x84", "\x85", "\x86", "\x87",
    "\x88", "\x89", "\x8a", "\x8b", "\x8c", "\x8d", "\x8e", "\x8f",
    "\x90", "\x91", "\x92", "\x93", "\x94", "\x95", "\x96", "\x97",
    "\x98", "\x99", "\x9a", "\x9b", "\x9c", "\x9d", "\x9e", "\x9f",
    "¶"   , "┴"   , "♥"   , "┐"   , "╡"   , "├"   , "└"   , "═"   ,
    "╤"   , "♠"   , "┌"   , "┬"   , "╨"   , "↓"   , "┼"   , "║"   ,
    "┤"   , "←"   , "╬"   , "↑"   , "♣"   , "─"   , "╫"   , "│"   ,
    "♦"   , "┘"   , "╪"   , "╥"   , "╧"   , "╞"   , "→"   , "▓"   ,
    "ю"   , "а"   , "б"   , "ц"   , "д"   , "е"   , "ф"   , "г"   ,
    "х"   , "и"   , "й"   , "к"   , "л"   , "м"   , "н"   , "о"   ,
    "п"   , "я"   , "р"   , "с"   , "т"   , "у"   , "ж"   , "в"   ,
    "ь"   , "ы"   , "з"   , "ш"   , "э"   , "щ"   , "ч"   , "ъ"   ,
    "Ю"   , "А"   , "Б"   , "Ц"   , "Д"   , "Е"   , "Ф"   , "Г"   ,
    "Х"   , "И"   , "Й"   , "К"   , "Л"   , "М"   , "Н"   , "О"   ,
    "П"   , "Я"   , "Р"   , "С"   , "Т"   , "У"   , "Ж"   , "В"   ,
    "Ь"   , "Ы"   , "З"   , "Ш"   , "Э"   , "Щ"   , "Ч"   , "Ъ"
]


ENCODING_TABLE = {char: i for i, chars in enumerate(DECODING_TABLE) for char in chars}




def encode(string: str, errors: str="strict"):
    assert errors == "strict"
    try:
        return bytes(ENCODING_TABLE[char] for char in string), len(string)
    except KeyError:
        start = 0
        while string[start] in ENCODING_TABLE:
            start += 1
        end = len(string)
        while string[end - 1] in ENCODING_TABLE:
            end -= 1
        raise UnicodeEncodeError("bk", string, start, end, "invalid character") from None


def decode(string: bytes, errors: str="strict"):
    assert errors == "strict"
    return "".join(DECODING_TABLE[char][0] for char in string), len(string)


def _search(name: str):
    if name == "bk":
        return codecs.CodecInfo(encode, decode, name="bk")
    else:
        return None


def register():
    codecs.register(_search)


register()
