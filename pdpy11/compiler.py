import collections
import struct
import sys

from .builtins import builtin_commands
from .containers import CaseInsensitiveDict
from .deferred import Promise, wait, BaseDeferred, Deferred, SizedDeferred, DeferredCycle
from .devices import open_device
from .formats import file_formats
from .metacommand_impl import get_as_int
from . import operators
from .types import Instruction, Label, Assignment, InstructionPointer, WordList, ParenthesizedExpression
from . import reports


class Compiler:
    def __init__(self, output_charset="bk"):
        self.symbols = CaseInsensitiveDict()
        self.extern_symbols_mapping = CaseInsensitiveDict()
        self.emitted_files = []
        self.output_charset = output_charset
        self.next_local_symbol_prefix = 1
        self.next_internal_symbol_prefix = 1
        self.times_file_compiled = collections.defaultdict(int)
        self.internal_prefix_to_state = {}


    def compile_file(self, file, start, link_base):
        self.times_file_compiled[file.filename] += 1
        state = {
            "filename": file.filename,
            "context": "file",
            "internal_symbol_prefix": f".internal{self.next_internal_symbol_prefix}.",
            "compiler": self,
            "link_base": link_base,
            "internal_symbols_list": [],
            "extern_all": None
        }
        self.internal_prefix_to_state[self.next_internal_symbol_prefix] = state
        self.next_internal_symbol_prefix += 1
        return self.compile_block(state, file.body, start)


    def compile_block(self, state, block, start):
        addr = start
        data = b""

        local_symbol_prefix = f".local{self.next_local_symbol_prefix}."
        self.next_local_symbol_prefix += 1

        try:
            for insn in block.insns:
                state = {**state, "insn": insn, "emit_address": addr, "local_symbol_prefix": local_symbol_prefix}
                if isinstance(insn, Instruction):
                    chunk = self.compile_insn(insn, state)
                    if chunk is not None:
                        data += chunk
                        if isinstance(chunk, BaseDeferred):
                            addr += chunk.length()
                        else:
                            addr += len(chunk)

                elif isinstance(insn, WordList):
                    chunk = self.compile_word_list(insn, insn.words, state)
                    data += chunk
                    if isinstance(chunk, BaseDeferred):
                        addr += chunk.length()
                    else:
                        addr += len(chunk)

                elif isinstance(insn, Label):
                    if state["context"] == "repeat":
                        if not hasattr(insn, "label_error_emitted"):
                            reports.error(
                                "unexpected-symbol-definition",
                                (insn.ctx_start, insn.ctx_end, "Labels cannot be defined inside '.repeat' loop")
                            )
                            insn.label_error_emitted = True
                        _ = 1  # for code coverage
                        continue

                    self.compile_label(insn, addr, state)
                    if not insn.local:
                        local_symbol_prefix = f".local{self.next_local_symbol_prefix}."
                        self.next_local_symbol_prefix += 1

                elif isinstance(insn, Assignment):
                    if isinstance(insn.target, InstructionPointer):
                        if state["link_base"]["promise"].settled:
                            # Bring the current address forward
                            def closure(insn):
                                nonlocal data, addr
                                def fn():
                                    old_addr_value = wait(addr)
                                    new_addr_value = get_as_int(state, "link address", state["insn"], insn.value, bitness=16, unsigned=False)
                                    length = new_addr_value - old_addr_value
                                    if length < 0:
                                        reports.error(
                                            "value-out-of-bounds",
                                            (insn.ctx_start, insn.ctx_end, f"The new link address is lower than the previous one: a negative skip from {old_addr_value} to {new_addr_value} was attempted")
                                        )
                                        raise reports.RecoverableError("A negative value was passed when an unsigned value was expected")
                                    return b"\x00" * length

                                chunk = Deferred[bytes](fn)
                                data += chunk
                                if isinstance(chunk, BaseDeferred):
                                    addr += chunk.length()
                                else:
                                    addr += len(chunk)
                            closure(insn)
                        else:
                            # Set link base
                            self.set_link_address(insn.value, state)
                        continue

                    if state["context"] == "repeat":
                        if not hasattr(insn, "assignment_error_emitted"):
                            reports.error(
                                "unexpected-symbol-definition",
                                (insn.ctx_start, insn.ctx_end, "Variables cannot be defined inside '.repeat' loop")
                            )
                            insn.assignment_error_emitted = True
                        _ = 1  # for code coverage
                        continue

                    self.compile_assignment(insn, state)

                else:
                    assert False  # pragma: no cover
        except CompilerStopIteration:
            pass

        return data


    def compile_label(self, label, addr, state):
        if label.local:
            name = state["local_symbol_prefix"] + label.name
        else:
            name = state["internal_symbol_prefix"] + label.name

        if name in self.symbols:
            prev_sym, _ = self.symbols[name]
            reports.error(
                "duplicate-symbol",
                (label.ctx_start, label.ctx_end, f"Duplicate {'local label' if label.local else 'symbol'} '{label.name}:'"),
                (prev_sym.ctx_start, prev_sym.ctx_end, "A symbol with the same name has been already declared here")
            )
            return

        self.symbols[name] = (label, addr)

        if label.is_extern:
            self.declare_external_symbol(label, label.name, state)

        if not label.local:
            state["internal_symbols_list"].append(label.name)
            if state["extern_all"]:
                self.declare_external_symbol(state["extern_all"], label.name, state)


    def compile_assignment(self, insn, state):
        name = state["internal_symbol_prefix"] + insn.target.name

        if name in self.symbols:
            prev_sym, _ = self.symbols[name]
            reports.error(
                "duplicate-symbol",
                (insn.ctx_start, insn.ctx_end, f"Duplicate variable '{insn.target.name}'"),
                (prev_sym.ctx_start, prev_sym.ctx_end, "A symbol with the same name has been already declared here")
            )
            return

        state["internal_symbols_list"].append(insn.target.name)
        self.symbols[name] = (insn, Deferred[int](lambda: insn.value.resolve(state), insn.target.name))

        if insn.is_extern:
            self.declare_external_symbol(insn, insn.target.name, state)

        if state["extern_all"]:
            self.declare_external_symbol(state["extern_all"], insn.target.name, state)


    def set_link_address(self, address, state):
        if state["link_base"]["promise"].settled:
            prev_link = state["link_base"]["set_where"]
            if prev_link is None:
                reports.error(
                    "address-conflict",
                    (state["insn"].ctx_start, state["insn"].ctx_end, "The link base cannot be set here because this metacommand cannot be evaluated\nbefore the link base itself is known.")
                )
            else:
                reports.error(
                    "address-conflict",
                    (state["insn"].ctx_start, state["insn"].ctx_end, "The link base has already been set."),
                    (prev_link.ctx_start, prev_link.ctx_end, "The link base has been previously set here.")
                )
            return

        def fn():
            try:
                return get_as_int(state, "link address", state["insn"], address, bitness=16, unsigned=False)
            except DeferredCycle:
                reports.error(
                    "recursive-definition",
                    (state["insn"].ctx_start, state["insn"].ctx_end, f"The link base is mathematically equal to {address.resolve(state)!r},\nwhere LA denotes link base. In other words, the link base depends on itself,\nand thus cannot be determined.")
                )
                return 0

        state["link_base"]["set_where"] = state["insn"]
        state["link_base"]["promise"].settle(Deferred[int](fn))


    def declare_external_symbol(self, location, name, state):
        if name in self.extern_symbols_mapping:
            previous_extern = self.extern_symbols_mapping[name][0]
            reports.error(
                "duplicate-symbol",
                (location.ctx_start, location.ctx_end, f"Duplicate external symbol '{name}'."),
                (previous_extern.ctx_start, previous_extern.ctx_end, "A symbol with the same name was previously declared external here.")
            )
        else:
            self.extern_symbols_mapping[name] = location, state["internal_symbol_prefix"] + name


    def compile_insn(self, insn, state):
        if insn.name.name in builtin_commands:
            return builtin_commands[insn.name.name].compile_insn(state, insn)
        elif "." + insn.name.name in builtin_commands:
            reports.warning(
                "meta-typo",
                (insn.name.ctx_start, insn.name.ctx_end, f"'{insn.name.name}' is not a metacommand by itself, but '.{insn.name.name}' is.\nPlease be explicit and add a dot."),
            )
            return builtin_commands["." + insn.name.name].compile_insn(state, insn)
        else:
            candidates = (state["internal_symbol_prefix"] + insn.name.name, insn.name.name)
            for name in candidates:
                if name in self.symbols:
                    # Resolve a macro
                    symbol, _ = self.symbols[name]

                    if isinstance(symbol, Label):
                        reports.error(
                            "meta-type-mismatch",
                            (insn.name.ctx_start, insn.name.ctx_end, f"'{insn.name.name}' is used as an instruction name"),
                            (symbol.ctx_start, symbol.ctx_end, "...but is defined as a label here. You might want to add '.word' or use macros.")
                        )
                        return None

                    elif isinstance(symbol, Assignment):
                        # Implicit .word
                        words = [insn.name] + insn.operands[:]
                        if len(words) > 1:
                            if isinstance(words[1], ParenthesizedExpression) and words[1].opening_parenthesis == "(":
                                # 'a (expr)' was misparsed as instruction 'a' with operand '(expr)'
                                # instead of '.word a(expr)', where 'a(expr)' is a call
                                words[0] = operators.call(words[0].ctx_start, words[1].ctx_end, words[0], words[1].expr)
                                words.pop(1)
                            else:
                                reports.error(
                                    "meta-type-mismatch",
                                    (words[0].ctx_start, words[0].ctx_end, f"'{insn.name.name}' is used as an instruction name"),
                                    (symbol.ctx_start, symbol.ctx_end, "...but is defined as a variable here. This would normally be interpreted as\nimplicit '.word', but the comma between the first and the second words is missing.")
                                )
                        return self.compile_word_list(insn, words, state)

                    else:
                        # TODO: macros
                        assert False  # pragma: no cover

            reports.error(
                "unknown-insn",
                (insn.name.ctx_start, insn.name.ctx_end, f"'{insn.name.name}' is an undefined {'metainstruction' if insn.name.name[0] == '.' else 'instruction'}.\nIs our database incomplete? Report that on GitHub: https://github.com/imachug/pdpy11/issues/new")
            )
            return None


    def compile_word_list(self, insn, insn_words, state):
        def fn():
            words = [get_as_int(state, "implicit word", insn, word, bitness=16, unsigned=False) for word in insn_words]
            prefix = b""
            if wait(state["emit_address"]) % 2 == 1:
                prefix = b"\x00"
                reports.error(
                    "odd-address",
                    (state["insn"].ctx_start, state["insn"].ctx_end, "This word list was emitted on an odd address.\nThe pointer was automatically adjusted one byte forward by inserting a null byte.\nThis may break labels and address calculation in your program;\nplease add '.even' or '.byte 0' where necessary.")
                )
            return prefix + b"".join(struct.pack("<H", word) for word in words)

        return SizedDeferred[bytes](2 * len(insn_words), fn)



    def compile_include(self, file, addr):
        link_base = {
            "promise": Promise[int](f"LA{self.next_internal_symbol_prefix}"),
            "set_where": None
        }

        code = self.compile_file(file, link_base["promise"], link_base)

        if not link_base["promise"].settled:
            link_base["promise"].settle(addr)

        return code


    def compile_and_link_files(self, files_ast):
        link_base = {
            "promise": Promise[int]("LA"),
            "set_where": None
        }

        addr = link_base["promise"]
        generated_code = b""

        for file_ast in files_ast:
            data = self.compile_file(file_ast, addr, link_base)
            generated_code += data
            if isinstance(data, BaseDeferred):
                addr += data.length()
            else:
                addr += len(data)

        if not link_base["promise"].settled:
            link_base["promise"].settle(0o1000)

        base, code = wait(link_base["promise"]), wait(generated_code)

        # Resolve all symbols, in case some have not been used
        for _, (_, value) in self.symbols.items():
            wait(value)

        return base, code


    def emit_files(self, base, code):
        if not self.emitted_files:
            return False, None

        for ctx_start, ctx_end, file_format, filepath, *arguments in self.emitted_files:
            result = file_formats[file_format](base, code, *arguments)
            try:
                with open_device(filepath, "wb") as f:
                    f.write(result)
            except IOError as ex:
                reports.error(
                    "io-error",
                    (ctx_start, ctx_end, f"Could not write to '{filepath}':\n{ex}")
                )
            else:
                print(f"File '{filepath}' was written in format '{file_format}'", file=sys.stderr)

        return True, {
            "format": self.emitted_files[0][2],
            "path": self.emitted_files[0][3]
        }


    def generate_listing(self):
        labels_by_file = collections.defaultdict(list)

        for name, (_, addr) in self.symbols.items():
            if name.startswith(".internal"):
                label_name = name[9:].partition(".")[2]

                internal_prefix = int(name[9:].partition(".")[0])
                state = self.internal_prefix_to_state[internal_prefix]
                filename = state["filename"]

                value = wait(addr)

                labels_by_file[filename].append((label_name, value))


        result = ""

        for filename, labels in labels_by_file.items():
            result += filename + "\n"

            labels.sort(key=lambda item: (item[1], item[0]))
            for name, value in labels:
                if isinstance(value, int):
                    result += oct(value)[2:].rjust(6, "0") + " " + name + "\n"

            result += "\n"

        return result


    def stop_iteration(self):
        raise CompilerStopIteration()


class CompilerStopIteration(Exception):
    pass
