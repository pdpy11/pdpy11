import inspect
import os
import struct

from .containers import CaseInsensitiveDict
from .deferred import Deferred, SizedDeferred, wait, BaseDeferred
from . import radix50
from . import operators
from . import reports
from . import types
from .types import CodeBlock


def get_as_int(state, what, token, arg_token, bitness, unsigned):
    value = wait(arg_token.resolve(state))
    if isinstance(value, int):
        if unsigned and value < 0:
            reports.error(
                "value-out-of-bounds",
                (arg_token.ctx_start, arg_token.ctx_end, f"An unsigned integer is expected as {what}, but {value} was passed")
            )
            raise reports.RecoverableError("A negative value was passed when an unsigned value was expected")
        if value <= -2 ** bitness:
            reports.error(
                "value-out-of-bounds",
                (arg_token.ctx_start, arg_token.ctx_end, f"The value is too small: {value} does not fit in {bitness} bits")
            )
            raise reports.RecoverableError("Too negative value")
        if value >= 2 ** bitness:
            reports.error(
                "value-out-of-bounds",
                (arg_token.ctx_start, arg_token.ctx_end, f"The value is too large: {value} does not fit in {bitness} bits")
            )
            raise reports.RecoverableError("Too large value")
        return value % (2 ** bitness)
    else:
        reports.error(
            "type-mismatch",
            (token.ctx_start, token.ctx_end, f"A number was expected as {what}"),
            (arg_token.ctx_start, arg_token.ctx_end, f"...yet the evaluated value is not an integer but {type(value).__name__}")
        )
        raise reports.RecoverableError()


def get_as_str(state, what, token, arg_token):
    value = wait(arg_token.resolve(state))
    if isinstance(value, str):
        return value
    else:
        reports.error(
            "type-mismatch",
            (token.ctx_start, token.ctx_end, f"A string was expected as {what}"),
            (arg_token.ctx_start, arg_token.ctx_end, f"...yet the evaluated value is not a string but {type(value).__name__}")
        )
        raise reports.RecoverableError()


from .insns import instructions  # pylint: disable=wrong-import-position
builtin_commands = CaseInsensitiveDict(instructions)


class Metacommand:
    def __init__(self, fn, name, size_fn=None, literal_string_operand=False):
        self.fn = fn
        self.size_fn = size_fn
        self.literal_string_operand = literal_string_operand
        self.name = name

        sig = inspect.signature(fn)
        assert list(sig.parameters.keys())[:1] == ["state"]

        self.min_operands = 0
        self.max_operands = 0
        self.takes_code_block = False
        self.operand_types = []
        for param in list(sig.parameters.values())[1:]:
            annotation = param.annotation
            assert annotation is not inspect.Parameter.empty
            if not isinstance(annotation, str):
                annotation = annotation.__name__
            self.operand_types.append(annotation)

            if param.annotation in (CodeBlock, "CodeBlock"):
                self.takes_code_block = True
                continue
            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                if param.default is inspect.Parameter.empty:
                    self.min_operands += 1
                self.max_operands += 1
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                self.max_operands = float("+inf")

        if literal_string_operand:
            assert 0 <= self.min_operands <= 1 and self.max_operands == 1, "A metacommand with a literal string operand is expected to have exactly one operand (optional or not)"


    def compile_insn(self, state, compiler, insn):
        state = {**state, "insn": insn, "compiler": compiler}

        insn_operands = insn.operands
        code_block = None

        if self.takes_code_block:
            if insn_operands and isinstance(insn_operands[-1], CodeBlock):
                code_block = insn_operands[-1]
                insn_operands = insn_operands[:-1]
            else:
                reports.error(
                    "wrong-meta-operands",
                    (insn.ctx_start, insn.ctx_end, f"Metacommand '{insn.name.name}' expects a code block, but it was not passed")
                )
                raise reports.RecoverableError("Code block not passed")

        if self.min_operands == self.max_operands:
            expectation = f"{self.max_operands} operand" + ("s" if self.max_operands >= 2 else "")
        elif self.max_operands == float("+inf"):
            expectation = f"at least {self.min_operands} operand" + ("s" if self.min_operands >= 2 else "")
        else:
            expectation = f"from {self.min_operands} to {self.max_operands} operand" + ("s" if self.max_operands >= 2 else "")

        if len(insn_operands) < self.min_operands:
            reports.error(
                "wrong-meta-operands",
                (insn.ctx_start, insn.ctx_end, f"Too few operands passed to '{insn.name.name}': {len(insn.operands)} passed, {expectation} expected")
            )
            raise reports.RecoverableError("Too few operands")
        elif len(insn_operands) > self.max_operands:
            reports.error(
                "wrong-meta-operands",
                (insn.ctx_start, insn.ctx_end, f"Too many operands passed to '{insn.name.name}': {len(insn.operands)} passed, {expectation} expected")
            )
            raise reports.RecoverableError("Too many operands")

        operands = []
        for operand in insn_operands:
            # Stupid pylint doesn't know that decorators can mutate types
            # pylint: disable=isinstance-second-argument-not-valid-type
            if isinstance(operand, operators.immediate):
                reports.error(
                    "excess-hash",
                    (operand.ctx_start, operand.ctx_end, f"Unexpected immediate value in '{self.name}' metacommand.\nYou wrote '{operand.text()}', you probably meant '{operand.operand.text()}', proceeding under that assumption"),
                    (insn.name.ctx_start, insn.name.ctx_end, "Metacommand started here")
                )
                operands.append(operand.operand)
            else:
                operands.append(operand)

        if code_block is not None:
            operands.append(code_block)

        def fn():
            return self.fn(state, *operands)
        if self.size_fn is None:
            return Deferred[bytes](fn)
        else:
            return SizedDeferred[bytes](self.size_fn(state, *operands), fn)


def _metacommand_impl(fn, no_dot=False, alias=None, **kwargs):
    name = ("" if no_dot else ".") + fn.__name__.rstrip("_")

    if isinstance(alias, str):
        aliases = [alias]
    elif alias is None:
        aliases = []
    else:
        aliases = alias

    cmd = Metacommand(fn, name, **kwargs)
    for alias in aliases + [name]:
        builtin_commands[alias] = cmd

    # That is not to override globals with the same name, e.g. list
    return __builtins__.get(fn.__name__, None)


def metacommand(fn=None, **kwargs):
    if fn is None:
        # This looks like a false positive from pylint
        return lambda fn: metacommand(fn, **kwargs)  # pylint: disable=unnecessary-lambda
    else:
        return _metacommand_impl(fn, **kwargs)


@metacommand(size_fn=lambda state, *operands: len(operands) or 1, alias=".db")
def byte(state, *operands: int) -> bytes:
    if not operands:
        reports.warning(
            "implicit-operand",
            (state["insn"].ctx_start, state["insn"].ctx_end, "'.byte' without an operand is implicitly treated as '.byte 0'.\nPlease consider inserting the zero explicitly.")
        )
        return b"\x00"
    def encode_i8(operand):
        value = get_as_int(state, "'.byte' operand", state["insn"], operand, bitness=8, unsigned=False)
        assert -2 ** 8 < value < 2 ** 8
        value %= 2 ** 8
        return struct.pack("<B", value)
    return b"".join(encode_i8(operand) for operand in operands)


@metacommand(size_fn=lambda state, *operands: 2 * (len(operands) or 1), alias=".dw")
def word(state, *operands: int) -> bytes:
    prefix = b""
    if wait(state["emit_address"]) % 2 == 1:
        prefix = b"\x00"
        reports.error(
            "odd-address",
            (state["insn"].ctx_start, state["insn"].ctx_end, "This '.word' was emitted on an odd address.\nThe pointer was automatically adjusted one byte forward by inserting a null byte.\nThis may break labels and address calculation in your program;\nplease add '.even' or '.byte 0' where necessary.")
        )
    if not operands:
        reports.warning(
            "implicit-operand",
            (state["insn"].ctx_start, state["insn"].ctx_end, "'.word' without an operand is implicitly treated as '.word 0'.\nPlease consider inserting the zero explicitly.")
        )
        return prefix + b"\x00\x00"
    def encode_i16(operand):
        value = get_as_int(state, "'.word' operand", state["insn"], operand, bitness=16, unsigned=False)
        assert -2 ** 16 < value < 2 ** 16
        value %= 2 ** 16
        return struct.pack("<H", value)
    return prefix + b"".join(encode_i16(operand) for operand in operands)


@metacommand(size_fn=lambda state, *operands: 4 * (len(operands) or 1))
def dword(state, *operands: int) -> bytes:
    prefix = b""
    if wait(state["emit_address"]) % 2 == 1:
        prefix = b"\x00"
        reports.error(
            "odd-address",
            (state["insn"].ctx_start, state["insn"].ctx_end, "This '.dword' was emitted on an odd address.\nThe pointer was automatically adjusted one byte forward by inserting a null byte.\nThis may break labels and address calculation in your program;\nplease add '.even' or '.byte 0' where necessary.")
        )
    if not operands:
        reports.warning(
            "implicit-operand",
            (state["insn"].ctx_start, state["insn"].ctx_end, "'.dword' without an operand is implicitly treated as '.dword 0'.\nPlease consider inserting the zero explicitly.")
        )
        return prefix + b"\x00\x00\x00\x00"
    def encode_i32(operand):
        value = get_as_int(state, "'.dword' operand", state["insn"], operand, bitness=32, unsigned=False)
        assert -2 ** 32 < value < 2 ** 32
        value %= 2 ** 32
        return struct.pack("<H", value >> 16) + struct.pack("<H", value & 0xffff)
    return prefix + b"".join(encode_i32(operand) for operand in operands)


# pylint: disable=redefined-builtin
@metacommand
def ascii_(state, operand: str) -> bytes:
    return get_as_str(state, "'.ascii' operand", state["insn"], operand).encode(state["compiler"].output_charset)


@metacommand
def asciz(state, operand: str) -> bytes:
    return get_as_str(state, "'.asciz' operand", state["insn"], operand).encode(state["compiler"].output_charset) + b"\x00"


@metacommand
def rad50(state, operand: str) -> bytes:
    if isinstance(operand, types.StringConcatenation):
        chunks = operand.chunks
    else:
        chunks = [operand]

    characters = []
    for chunk in chunks:
        if isinstance(chunk, types.AngleBracketedChar):
            # Raw number in range 0:50 (octal)
            val = wait(chunk.expr.resolve(state))
            if not 0 <= val < 40:
                reports.error(
                    "value-out-of-bounds",
                    (chunk.ctx_start, chunk.ctx_end, f"Character {val} cannot be packed into a radix-50 word.\nA value in range [0; 50) is expected (decimal).")
                )
                val = 0
            characters.append(val)
        else:
            string = get_as_str(state, "'.rad50' operand", state["insn"], chunk)
            for char in string:
                try:
                    val = radix50.TABLE.index(char.upper())
                except ValueError:
                    reports.error(
                        "invalid-character",
                        (chunk.ctx_start, chunk.ctx_end, f"Character '{char}' cannot be converted using radix-50.\nThe supported characters are: ' ABCDEFGHIJKLMNOPQRSTUVWXYZ$.%0123456789'.")
                    )
                    val = 0
                characters.append(val)

    while len(characters) % 3 != 0:
        characters.append(0)

    result = b""
    for i in range(0, len(characters), 3):
        a, b, c = characters[i:i + 3]
        result += struct.pack("<H", a * 1600 + b * 40 + c)
    return result


@metacommand
def blkb(state, cnt: int) -> bytes:
    cnt_val = get_as_int(state, "'.blkb' count", state["insn"], cnt, 16, unsigned=True)
    return b"\x00" * cnt_val


@metacommand
def blkw(state, cnt: int) -> bytes:
    cnt_val = get_as_int(state, "'.blkw' count", state["insn"], cnt, 16, unsigned=True)
    return b"\x00\x00" * cnt_val


@metacommand
def even(state) -> bytes:
    return b"\x00" if wait(state["emit_address"]) % 2 == 1 else b""


@metacommand
def odd(state) -> bytes:
    # As if that's any useful...
    return b"\x00" if wait(state["emit_address"]) % 2 == 0 else b""


# TODO: Macro-11 seems to have .rept metacommand. That is probably the same as
# .repeat but '.rept X [code] .endr' instead of '.repeat X { [code] }'
@metacommand
def repeat(state, cnt: int, body: CodeBlock) -> bytes:
    addr = state["emit_address"]
    result = b""
    cnt_val = wait(cnt.resolve(state))
    if cnt_val < 0:
        reports.error(
            "value-out-of-bounds",
            (cnt.ctx_start, cnt.ctx_end, f"Repetitions count cannot be negative ({cnt_val} given)")
        )
    for _ in range(cnt_val):
        chunk = state["compiler"].compile_block({**state, "context": "repeat"}, body, addr)
        if isinstance(chunk, BaseDeferred):
            addr += chunk.length()
        else:
            addr += len(chunk)
        result += chunk
    return result


@metacommand(literal_string_operand=True)
def error_(state, error: str=None) -> bytes:
    reports.error(
        "user-error",
        (state["insn"].ctx_start,state["insn"].ctx_end, "Error" + (f": {error!r}" if error else ""))
    )
    return b""


@metacommand
def list_(state, _: int=None) -> bytes:
    # TODO: Does it make sense to implement this stuff?
    reports.warning(
        "not-implemented",
        (state["insn"].ctx_start, state["insn"].ctx_end, ".list metacommand is not supported by pdpy")
    )
    return b""


@metacommand
def nlist(state, _: int=None) -> bytes:
    # TODO: Does it make sense to implement this stuff?
    reports.warning(
        "not-implemented",
        (state["insn"].ctx_start, state["insn"].ctx_end, ".nlist metacommand is not supported by pdpy")
    )
    return b""


@metacommand(literal_string_operand=True)
def title_(state, title: str) -> bytes:
    # TODO: handle this
    reports.warning(
        "not-implemented",
        (state["insn"].ctx_start, state["insn"].ctx_end, ".title metacommand is not supported by pdpy")
    )
    return b""


@metacommand(literal_string_operand=True)
def sbttl(state, text: str) -> bytes:
    # TODO: handle this
    reports.warning(
        "not-implemented",
        (state["insn"].ctx_start, state["insn"].ctx_end, ".sbttl metacommand is not supported by pdpy")
    )
    return b""


@metacommand
def ident(state, identification: str) -> bytes:
    # TODO: handle this
    reports.warning(
        "not-implemented",
        (state["insn"].ctx_start, state["insn"].ctx_end, ".ident metacommand is not supported by pdpy")
    )
    return b""


@metacommand
def page(state) -> bytes:
    # TODO: handle this
    reports.warning(
        "not-implemented",
        (state["insn"].ctx_start, state["insn"].ctx_end, ".page metacommand is not supported by pdpy")
    )
    return b""


@metacommand(no_dot=True)
def insert_file(state, filepath: str) -> bytes:
    path = get_as_str(state, "'insert_file' path", state["insn"], filepath)
    include_path = os.path.abspath(os.path.join(os.path.dirname(state["filename"]), path))
    try:
        with open(include_path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        reports.error(
            "io-error",
            (filepath.ctx_start, filepath.ctx_end, f"There is no file at path '{include_path}'. Double-check file paths?")
        )
    except IsADirectoryError:
        reports.error(
            "io-error",
            (filepath.ctx_start, filepath.ctx_end, f"The file at path '{include_path}' is a directory.")
        )
    except IOError:
        reports.error(
            "io-error",
            (filepath.ctx_start, filepath.ctx_end, f"Could not read file at path '{include_path}'.")
        )
    return b""


def add_emitted_file(state, filepath, insn_name, file_format, file_extension, *args):
    if filepath is not None:
        path = get_as_str(state, f"'{insn_name}' path", state["insn"], filepath)
        write_path = os.path.abspath(os.path.join(os.path.dirname(state["filename"]), path))
    else:
        write_path = state["filename"]
        if write_path.lower().endswith(".mac"):
            write_path = write_path[:-4]
        if file_extension is not None:
            write_path += f".{file_extension}"
    state["compiler"].emitted_files.append((state["insn"].ctx_start, state["insn"].ctx_end, file_format, write_path, *args))


@metacommand(no_dot=True)
def make_bin(state, filepath: str=None) -> bytes:
    add_emitted_file(state, filepath, "make_bin", "bin", "bin")
    return b""


@metacommand(no_dot=True)
def make_raw(state, filepath: str=None) -> bytes:
    add_emitted_file(state, filepath, "make_raw", "raw", None)
    return b""


def add_emitted_bk_wav(state, filepath, bk_filename, insn_name, file_format):
    if filepath is not None:
        filepath = get_as_str(state, f"'{insn_name}' output wav path", state["insn"], filepath)
        write_path = os.path.abspath(os.path.join(os.path.dirname(state["filename"]), filepath))
    else:
        write_path = state["filename"]
        if write_path.lower().endswith(".mac"):
            write_path = write_path[:-4]
        write_path += ".wav"

    if bk_filename is None:
        bk_filename = write_path.split("/")[-1]
        if bk_filename.lower().endswith(".wav"):
            bk_filename = bk_filename[:-4]
        encoded_bk_filename = bk_filename.encode(state["compiler"].output_charset)
        if len(encoded_bk_filename) > 16:
            reports.error(
                "too-long-string",
                (state["insn"].ctx_start, state["insn"].ctx_end, f"The BK tape file has a header that contains a 16-byte filename.\nThe filename for this file was inferred from the output file to be '{bk_filename}',\nwhich does not fit in 16 bytes. You can set the filename manually like this:\n{insn_name} 'output.wav', 'bk file name'\nChanging the output charset may help too, if the filename contains non-ASCII characters.")
            )
            encoded_bk_filename = encoded_bk_filename[:16]
    else:
        bk_filename = get_as_str(state, f"'{insn_name}' BK file name", state["insn"], bk_filename)
        encoded_bk_filename = bk_filename.encode(state["compiler"].output_charset)
        if len(encoded_bk_filename) > 16:
            reports.error(
                "too-long-string",
                (state["insn"].ctx_start, state["insn"].ctx_end, f"The BK filename does not fit in 16 bytes ('{bk_filename}').\nPlease truncate the filename. Changing the output charset may help too, if the filename contains non-ASCII characters.")
            )
            encoded_bk_filename = encoded_bk_filename[:16]

    encoded_bk_filename = encoded_bk_filename.ljust(16, b" ")

    state["compiler"].emitted_files.append((state["insn"].ctx_start, state["insn"].ctx_end, file_format, write_path, encoded_bk_filename))


@metacommand(no_dot=True)
def make_wav(state, filepath: str=None, bk_filename: str=None) -> bytes:
    add_emitted_bk_wav(state, filepath, bk_filename, "make_wav", "bk_wav")
    return b""


@metacommand(no_dot=True)
def make_turbo_wav(state, filepath: str=None, bk_filename: str=None) -> bytes:
    add_emitted_bk_wav(state, filepath, bk_filename, "make_turbo_wav", "bk_turbo_wav")
    return b""


@metacommand(size_fn=lambda state, address: 0)
def link(state, address: int) -> bytes:
    address_value = get_as_int(state, "'.link' operand", state["insn"], address, bitness=16, unsigned=False)
    compiler = state["compiler"]
    if not compiler.link_base.settled:
        compiler.link_base.settle(address_value)
    else:
        if compiler.link_base_set_where is None:
            reports.error(
                "recursive-definition",
                (state["insn"].ctx_start, state["insn"].ctx_end, f"The argument of '.link' directive is mathematically equal to {address.resolve(state)!r},\nwhere LA denotes link base. In other words, the link base depends on itself,\nand thus cannot be determined.")
            )
        else:
            prev_link = compiler.link_base_set_where
            reports.error(
                "address-conflict",
                (state["insn"].ctx_start, state["insn"].ctx_end, "A '.link' directive was encountered, but the link base has already been set."),
                (prev_link.ctx_start, prev_link.ctx_end, "The link address has been previously configured here.")
            )
    return b""

# TODO: Macro-11 has .print metacommand which we can probably ignore as Rhialto's implementation does

# TODO: implement .radix. Macro-11 supports only radix 8, 10, 16 and 2 but we
# can probably be more loose

# TODO: What's .flt4 / .flt2?

# TODO: .save and .restore

# TODO: .narg, .nchr, .ntype

# TODO: Support .include. Unlike pdp11asm's '.include', it is recursive, i.e.
# you can have code after '.include' and it will be compiled. That's where we're
# different from pdp11asm and pdpy in pdp11asm-compatible mode, but you really
# shouldn't have relied on that behavior (and we can always emit a warning
# in pdp11asm compatibility mode or something anyway)

# TODO: .irp, .irpc (what's that?)

# TODO: .library, .mcall, .macro, .mexit, .endm

# TODO: .enabl and .disable for options: ama, lsb, gbl, lc, lcm and probably
# others.
#   ama means 'interpret X as @#X'
#   gbl means 'treat undefined symbols as imported globals'
# No idea what other options mean.
# lsb seems to be handled for labels ending with a dollar, e.g. '1$' is
# implicitly transformed to '1$[lsb]' where [lsb] is the current lsb value

# TODO: .limit

# TODO: .end seems to take an optional operand?

# TODO: conditionals: .ifdf, .iif, .if, .iff, .ift, .iftf, .endc

# TODO: sections: .asect, .csect, .psect

# TODO: .weak and .globl, no idea what .weak means

# TODO: .byte and .word may take null arguments, e.g. '.word ,5' is the same as
# '.word 0, 5'
