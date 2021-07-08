import inspect
import struct
import typing

from .containers import CaseInsensitiveDict
from .deferred import Deferred, SizedDeferred, wait, BaseDeferred
from . import devices
from . import radix50
from . import operators
from . import reports
from . import types
from .types import CodeBlock


uint = typing.NewType("uint", int)
uint8 = typing.NewType("uint8", int)
uint16 = typing.NewType("uint16", int)
uint32 = typing.NewType("uint32", int)
int8 = typing.NewType("int8", int)
int16 = typing.NewType("int16", int)
int32 = typing.NewType("int32", int)


def get_as_int(state, what, token, arg_token, bitness, unsigned):
    value = wait(arg_token.resolve(state))
    if isinstance(value, int):
        if unsigned and value < 0:
            reports.error(
                "value-out-of-bounds",
                (arg_token.ctx_start, arg_token.ctx_end, f"An unsigned integer is expected as {what}, but {value} was passed")
            )
            raise reports.RecoverableError("A negative value was passed when an unsigned value was expected")
        if bitness is not None:
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
            return value
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
            (token.ctx_start, token.ctx_end, f"A string was expected for {what}"),
            (arg_token.ctx_start, arg_token.ctx_end, f"...yet the evaluated value is not a string but {type(value).__name__}")
        )
        raise reports.RecoverableError()


from .insns import instructions  # pylint: disable=wrong-import-position
builtin_commands = CaseInsensitiveDict(instructions)


if hasattr(typing, "get_origin"):  # pragma: no cover
    typing_get_origin = typing.get_origin
    typing_get_args = typing.get_args
elif hasattr(typing, "_GenericAlias"):
    def typing_get_origin(tp):
        if isinstance(tp, typing._GenericAlias):
            return tp.__origin__
        else:
            return None
    def typing_get_args(tp):
        if isinstance(tp, typing._GenericAlias):
            return tp.__args__
        else:
            return ()
elif hasattr(typing, "Union"):
    def typing_get_origin(tp):
        if str(type(tp)) == "typing.Union":
            return tp.__origin__
        else:
            return None
    def typing_get_args(tp):
        if str(type(tp)) == "typing.Union":
            return tp.__args__
        else:
            return ()
else:
    raise NotImplementedError("Unsupported version of Python")


class Metacommand:
    def __init__(self, fn, name, size=None, literal_string_operand=False, raw=False):
        self.fn = fn
        self.size = size
        self.literal_string_operand = literal_string_operand
        self.name = name
        self.raw = raw

        hints = typing.get_type_hints(fn)
        sig = inspect.signature(fn)
        assert list(sig.parameters.keys())[:1] == ["state"]

        self.min_operands = 0
        self.max_operands = 0
        self.takes_code_block = False
        self.operand_info = []

        for param in list(sig.parameters.values())[1:]:
            hint = hints[param.name]
            if typing_get_origin(hint) is typing.Union:
                hint, = [case for case in typing_get_args(hint) if case is not type(None)]
            self.operand_info.append({
                "type": hint.__supertype__ if hasattr(hint, "__supertype__") else hint,
                "hint": hint,
                "name": param.name
            })

            if hint is CodeBlock:
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


    def compile_insn(self, state, insn):
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
            if self.raw:
                cooked_operands = operands
            else:
                cooked_operands = []

                for i, operand in enumerate(operands):
                    operand_info = self.operand_info[min(i, len(self.operand_info) - 1)]
                    comment = operand_info["name"].replace("_", " ")

                    if operand_info["type"] is str:
                        cooked_operand = get_as_str(state, comment, state["insn"], operand)
                    elif operand_info["type"] is int:
                        type_name = operand_info["hint"].__name__
                        unsigned = type_name.startswith("u")
                        bitness_str = type_name.replace("u", "").replace("int", "")
                        bitness = int(bitness_str) if bitness_str else None
                        cooked_operand = get_as_int(state, comment, state["insn"], operand, bitness=bitness, unsigned=unsigned)
                    elif operand_info["type"] is CodeBlock:
                        cooked_operand = operand
                    else:
                        raise TypeError(f"Invalid operand type {operand_info['type']}")  # pragma: no cover

                    cooked_operands.append(cooked_operand)

            try:
                return self.fn(state, *cooked_operands)
            except reports.RecoverableError:
                return b""


        size = self.size(state, *operands) if callable(self.size) else self.size
        if size is None:
            return Deferred[bytes](fn)
        else:
            return SizedDeferred[bytes](size, fn)


def _metacommand_impl(fn, no_dot=False, alias=None, **kwargs):
    name = ("" if no_dot else ".") + fn.__name__.rstrip("_")

    if isinstance(alias, str):
        aliases = [alias]
    elif alias is None:
        aliases = []
    else:
        aliases = alias

    cmd = Metacommand(fn, name, **kwargs)
    for command_name in aliases + [name]:
        builtin_commands[command_name] = cmd

    # That is not to override globals with the same name, e.g. list
    return __builtins__.get(fn.__name__, None)


def metacommand(fn=None, **kwargs):
    if fn is None:
        # This looks like a false positive from pylint
        return lambda fn: metacommand(fn, **kwargs)  # pylint: disable=unnecessary-lambda
    else:
        return _metacommand_impl(fn, **kwargs)


@metacommand(size=lambda state, *operands: len(operands) or 1, alias=".db")
def byte(state, *byte_operand: int8) -> bytes:
    if not byte_operand:
        reports.warning(
            "implicit-operand",
            (state["insn"].ctx_start, state["insn"].ctx_end, "'.byte' without an operand is implicitly treated as '.byte 0'.\nPlease consider inserting the zero explicitly.")
        )
        return b"\x00"
    return b"".join(struct.pack("<B", operand) for operand in byte_operand)


@metacommand(size=lambda state, *operands: 2 * (len(operands) or 1), alias=".dw")
def word(state, *word_operand: int16) -> bytes:
    prefix = b""
    if wait(state["emit_address"]) % 2 == 1:
        prefix = b"\x00"
        reports.error(
            "odd-address",
            (state["insn"].ctx_start, state["insn"].ctx_end, "This '.word' was emitted on an odd address.\nThe pointer was automatically adjusted one byte forward by inserting a null byte.\nThis may break labels and address calculation in your program;\nplease add '.even' or '.byte 0' where necessary.")
        )
    if not word_operand:
        reports.warning(
            "implicit-operand",
            (state["insn"].ctx_start, state["insn"].ctx_end, "'.word' without an operand is implicitly treated as '.word 0'.\nPlease consider inserting the zero explicitly.")
        )
        return prefix + b"\x00\x00"
    return prefix + b"".join(struct.pack("<H", operand) for operand in word_operand)


@metacommand(size=lambda state, *operands: 4 * (len(operands) or 1))
def dword(state, *dword_operand: int32) -> bytes:
    prefix = b""
    if wait(state["emit_address"]) % 2 == 1:
        prefix = b"\x00"
        reports.error(
            "odd-address",
            (state["insn"].ctx_start, state["insn"].ctx_end, "This '.dword' was emitted on an odd address.\nThe pointer was automatically adjusted one byte forward by inserting a null byte.\nThis may break labels and address calculation in your program;\nplease add '.even' or '.byte 0' where necessary.")
        )
    if not dword_operand:
        reports.warning(
            "implicit-operand",
            (state["insn"].ctx_start, state["insn"].ctx_end, "'.dword' without an operand is implicitly treated as '.dword 0'.\nPlease consider inserting the zero explicitly.")
        )
        return prefix + b"\x00\x00\x00\x00"
    def encode_i32(value):
        return struct.pack("<H", value >> 16) + struct.pack("<H", value & 0xffff)
    return prefix + b"".join(encode_i32(operand) for operand in dword_operand)


# pylint: disable=redefined-builtin
@metacommand
def ascii_(state, ascii_text: str) -> bytes:
    try:
        return ascii_text.encode(state["compiler"].output_charset)
    except UnicodeEncodeError as ex:
        reports.error(
            "invalid-character",
            (state["insn"].ctx_start, state["insn"].ctx_end, f"Cannot encode this string using the selected output charset:\n{ex}\nYou can change the charset using --charset CLI argument or '.charset' directive.")
        )
        return b""


@metacommand
def asciz(state, ascii_text: str) -> bytes:
    try:
        return ascii_text.encode(state["compiler"].output_charset) + b"\x00"
    except UnicodeEncodeError as ex:
        reports.error(
            "invalid-character",
            (state["insn"].ctx_start, state["insn"].ctx_end, f"Cannot encode this string using the selected output charset:\n{ex}\nYou can change the charset using --charset CLI argument or '.charset' directive.")
        )
        return b""


@metacommand(raw=True)
def rad50(state, string: str) -> bytes:
    if isinstance(string, types.StringConcatenation):
        chunks = string.chunks
    else:
        chunks = [string]

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
def blkb(state, blkb_count: uint16) -> bytes:
    return b"\x00" * blkb_count


@metacommand
def blkw(state, blkw_count: uint16) -> bytes:
    return b"\x00\x00" * blkw_count


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
def repeat(state, repetitions_count: uint, body: CodeBlock) -> bytes:
    addr = state["emit_address"]
    result = b""
    for _ in range(repetitions_count):
        chunk = state["compiler"].compile_block({**state, "context": "repeat"}, body, addr)
        if isinstance(chunk, BaseDeferred):
            addr += chunk.length()
        else:
            addr += len(chunk)
        result += chunk
    return result


@metacommand(size=0, literal_string_operand=True)
def error_(state, error: str=None) -> bytes:
    reports.error(
        "user-error",
        (state["insn"].ctx_start,state["insn"].ctx_end, "Error" + (f": {error}" if error else ""))
    )
    return b""


@metacommand(size=0)
def list_(state, _: int=None) -> bytes:
    # TODO: Does it make sense to implement this stuff?
    reports.warning(
        "not-implemented",
        (state["insn"].ctx_start, state["insn"].ctx_end, ".list metacommand is not supported by pdpy")
    )
    return b""


@metacommand(size=0)
def nlist(state, _: int=None) -> bytes:
    # TODO: Does it make sense to implement this stuff?
    reports.warning(
        "not-implemented",
        (state["insn"].ctx_start, state["insn"].ctx_end, ".nlist metacommand is not supported by pdpy")
    )
    return b""


@metacommand(size=0, literal_string_operand=True)
def title_(state, title: str) -> bytes:  # pylint: disable=unused-argument
    # TODO: handle this
    reports.warning(
        "not-implemented",
        (state["insn"].ctx_start, state["insn"].ctx_end, ".title metacommand is not supported by pdpy")
    )
    return b""


@metacommand(size=0, literal_string_operand=True)
def sbttl(state, text: str) -> bytes:  # pylint: disable=unused-argument
    # TODO: handle this
    reports.warning(
        "not-implemented",
        (state["insn"].ctx_start, state["insn"].ctx_end, ".sbttl metacommand is not supported by pdpy")
    )
    return b""


@metacommand(size=0)
def ident(state, identification: str) -> bytes:  # pylint: disable=unused-argument
    # TODO: handle this
    reports.warning(
        "not-implemented",
        (state["insn"].ctx_start, state["insn"].ctx_end, ".ident metacommand is not supported by pdpy")
    )
    return b""


@metacommand(size=0)
def page(state) -> bytes:
    # TODO: handle this
    reports.warning(
        "not-implemented",
        (state["insn"].ctx_start, state["insn"].ctx_end, ".page metacommand is not supported by pdpy")
    )
    return b""


@metacommand(no_dot=True)
def insert_file(state, inserted_file_path: str) -> bytes:
    include_path = devices.resolve_relative_path(inserted_file_path, state["filename"])
    try:
        with open(include_path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        reports.error(
            "io-error",
            (state["insn"].ctx_start, state["insn"].ctx_end, f"There is no file at path '{include_path}'. Double-check file paths?")
        )
    except IsADirectoryError:
        reports.error(
            "io-error",
            (state["insn"].ctx_start, state["insn"].ctx_end, f"The file at path '{include_path}' is a directory.")
        )
    except IOError:
        reports.error(
            "io-error",
            (state["insn"].ctx_start, state["insn"].ctx_end, f"Could not read file at path '{include_path}'.")
        )
    return b""


def add_emitted_file(state, file_path, file_format, file_extension):
    if file_path is not None:
        write_path = devices.resolve_relative_path(file_path, state["filename"])
    else:
        write_path = state["filename"]
        if write_path.lower().endswith(".mac"):
            write_path = write_path[:-4]
        if file_extension is not None:
            write_path += f".{file_extension}"
    state["compiler"].emitted_files.append((state["insn"].ctx_start, state["insn"].ctx_end, file_format, write_path))


@metacommand(size=0, no_dot=True)
def make_bin(state, bin_file_path: str=None) -> bytes:
    add_emitted_file(state, bin_file_path, "bin", "bin")
    return b""


@metacommand(size=0, no_dot=True)
def make_bk0010_rom(state, bin_file_path: str=None) -> bytes:
    # For compatibility with pdp11asm
    add_emitted_file(state, bin_file_path, "bin", "bin")
    return b""


@metacommand(size=0, no_dot=True)
def make_raw(state, raw_file_path: str=None) -> bytes:
    add_emitted_file(state, raw_file_path, "raw", None)
    return b""


def add_emitted_bk_wav(state, output_wav_path, bk_filename, file_format):
    insn_name = state["insn"].name
    if output_wav_path is not None:
        write_path = devices.resolve_relative_path(output_wav_path, state["filename"])
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
        encoded_bk_filename = bk_filename.encode(state["compiler"].output_charset)
        if len(encoded_bk_filename) > 16:
            reports.error(
                "too-long-string",
                (state["insn"].ctx_start, state["insn"].ctx_end, f"The BK filename does not fit in 16 bytes ('{bk_filename}').\nPlease truncate the filename. Changing the output charset may help too, if the filename contains non-ASCII characters.")
            )
            encoded_bk_filename = encoded_bk_filename[:16]

    encoded_bk_filename = encoded_bk_filename.ljust(16, b" ")

    state["compiler"].emitted_files.append((state["insn"].ctx_start, state["insn"].ctx_end, file_format, write_path, encoded_bk_filename))


@metacommand(size=0, no_dot=True)
def make_wav(state, output_wav_path: str=None, file_name_on_tape: str=None) -> bytes:
    add_emitted_bk_wav(state, output_wav_path, file_name_on_tape, "bk_wav")
    return b""


@metacommand(size=0, no_dot=True)
def make_turbo_wav(state, output_wav_path: str=None, file_name_on_tape: str=None) -> bytes:
    add_emitted_bk_wav(state, output_wav_path, file_name_on_tape, "bk_turbo_wav")
    return b""


@metacommand(size=0, raw=True)
def link(state, address: int) -> bytes:
    compiler = state["compiler"]

    if state["link_base"]["promise"].settled:
        if state["link_base"]["set_where"] is None:
            reports.error(
                "recursive-definition",
                (state["insn"].ctx_start, state["insn"].ctx_end, f"The argument of '.link' directive is mathematically equal to {address.resolve(state)!r},\nwhere LA denotes link base. In other words, the link base depends on itself,\nand thus cannot be determined.")
            )
        else:
            prev_link = state["link_base"]["set_where"]
            reports.error(
                "address-conflict",
                (state["insn"].ctx_start, state["insn"].ctx_end, "A '.link' directive was encountered, but the link base has already been set."),
                (prev_link.ctx_start, prev_link.ctx_end, "The link address has been previously configured here.")
            )
        return b""

    address_value = get_as_int(state, "link address", state["insn"], address, bitness=16, unsigned=False)
    state["link_base"]["promise"].settle(address_value)
    state["link_base"]["set_where"] = state["insn"]
    return b""


@metacommand(size=0)
def include(state, included_file_path: str):
    include_path = devices.resolve_relative_path(included_file_path, state["filename"])

    try:
        with open(include_path, "r") as f:
            code = f.read()
    except FileNotFoundError:
        reports.error(
            "io-error",
            (state["insn"].ctx_start, state["insn"].ctx_end, f"There is no file at path '{include_path}'. Double-check file paths?")
        )
        return b""
    except IsADirectoryError:
        reports.error(
            "io-error",
            (state["insn"].ctx_start, state["insn"].ctx_end, f"The file at path '{include_path}' is a directory.")
        )
        return b""
    except IOError:
        reports.error(
            "io-error",
            (state["insn"].ctx_start, state["insn"].ctx_end, f"Could not read file at path '{include_path}'.")
        )
        return b""
    except UnicodeDecodeError as ex:
        reports.error(
            "io-error",
            (state["insn"].ctx_start, state["insn"].ctx_end, f"Source file '{include_path}' is not in UTF-8:\n{ex}")
        )
        return b""

    from . import parser
    file_ast = parser.parse(include_path, code)

    code = state["compiler"].compile_include(file_ast, state["emit_address"])

    return code


@metacommand(size=0, raw=True)
def extern(state, *symbol_name: int):
    compiler = state["compiler"]


    for symbol in symbol_name:
        if not isinstance(symbol, types.Symbol):
            reports.error(
                "meta-type-mismatch",
                (symbol.ctx_start, symbol.ctx_end, "A symbol name is expected as an argument to '.extern' directive")
            )
            continue

        if symbol.name.lower() == "all":
            for name in state["internal_symbols_list"]:
                compiler.declare_external_symbol(symbol, name, state)
            state["extern_all"] = True
        else:
            compiler.declare_external_symbol(symbol, symbol.name, state)

    return b""


@metacommand(size=0)
def end(state):
    state["compiler"].stop_iteration()


@metacommand(size=0)
def once(state):
    if state["compiler"].times_file_compiled[state["filename"]] > 1:
        state["compiler"].stop_iteration()
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
