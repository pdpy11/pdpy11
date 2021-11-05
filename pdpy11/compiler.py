import collections
import sys

from .builtins import builtin_commands
from .containers import CaseInsensitiveDict
from .deferred import Promise, wait, BaseDeferred, Deferred
from .devices import open_device
from .formats import file_formats
from .types import Instruction, Label, Assignment
from . import reports


class Compiler:
    def __init__(self, output_charset="bk"):
        self.symbols = CaseInsensitiveDict()
        self.extern_symbols_mapping = CaseInsensitiveDict()
        self.on_symbol_defined_listeners = CaseInsensitiveDict()
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
        self._handle_new_symbol(name)

        if not label.local:
            state["internal_symbols_list"].append(label.name)
            if state["extern_all"]:
                self.declare_external_symbol(state["extern_all"], label.name, state)


    def compile_assignment(self, var, state):
        name = state["internal_symbol_prefix"] + var.name.name

        if name in self.symbols:
            prev_sym, _ = self.symbols[name]
            reports.error(
                "duplicate-symbol",
                (var.ctx_start, var.ctx_end, f"Duplicate variable '{var.name.name}'"),
                (prev_sym.ctx_start, prev_sym.ctx_end, "A symbol with the same name has been already declared here")
            )
            return

        state["internal_symbols_list"].append(var.name.name)
        self.symbols[name] = (var, Deferred[int](lambda: var.value.resolve(state), var.name.name))
        self._handle_new_symbol(name)

        if state["extern_all"]:
            self.declare_external_symbol(state["extern_all"], var.name.name, state)


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
            self._handle_new_symbol(name)


    def _handle_new_symbol(self, name):
        for deferred in self.on_symbol_defined_listeners.get(name, []):
            if not deferred.is_awaiting:
                deferred.try_compute()


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
                    # TODO: pdpy in Macro-11 compatibility mode should support implicit
                    # .word directive. That is when 'x = 5; x' is the same as
                    # 'x = 5; .word x'. This is probably the right place to add the
                    # check.
                    if isinstance(symbol, Label):
                        reports.error(
                            "meta-type-mismatch",
                            (insn.name.ctx_start, insn.name.ctx_end, f"'{insn.name.name}' is used as an instruction name"),
                            (symbol.ctx_start, symbol.ctx_end, "...but is defined as a label here. Are you looking for macros?")
                        )
                        return None
                    elif isinstance(symbol, Assignment):
                        reports.error(
                            "meta-type-mismatch",
                            (insn.name.ctx_start, insn.name.ctx_end, f"'{insn.name.name}' is used as an instruction name"),
                            (symbol.ctx_start, symbol.ctx_end, "...but is defined as a constant here. You may be looking for MACRO-11 macros.\nNote that macros can also be defined implicitly using syntax like 'macro_name = .word 123'. Did you make a typo?")
                        )
                        return None
                    else:
                        # TODO: macros
                        assert False  # pragma: no cover

            reports.error(
                "unknown-insn",
                (insn.name.ctx_start, insn.name.ctx_end, f"'{insn.name.name}' is an undefined {'metainstruction' if insn.name.name[0] == '.' else 'instruction'}.\nIs our database incomplete? Report that on GitHub: https://github.com/imachug/pdpy11/issues/new")
            )
            return None


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

        return wait(link_base["promise"]), wait(generated_code)


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
