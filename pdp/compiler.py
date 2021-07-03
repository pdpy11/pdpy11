from .builtins import builtins
from .containers import CaseInsensitiveDict
from .deferred import Promise, wait, BaseDeferred
from .types import Instruction, Label, Assignment
from . import reports


class Compiler:
    def __init__(self):
        self.symbols = CaseInsensitiveDict()
        self.link_base: Promise = Promise[int]("LA")
        self.cur_emit_location = self.link_base
        self.generated_code = b""
        self.files = []


    def compile_file(self, file, start):
        return self.compile_block(file.body, start, "file")


    def compile_block(self, block, start, context):
        addr = start
        data = b""

        local_symbols = CaseInsensitiveDict()

        for insn in block.insns:
            if isinstance(insn, Instruction) and insn.name.name.lower() in (".end", "end"):
                if insn.name.name.lower() == "end":
                    reports.warning(
                        "meta-typo",
                        (insn.name.ctx_start, insn.name.ctx_end, f"'{insn.name.name}' is not a metacommand by itself, but '.{insn.name.name}' is.\nPlease be explicit and add a dot."),
                    )
                break

            state = {"emit_address": addr, "local_symbols": local_symbols, "compiler": self}
            if isinstance(insn, Instruction):
                chunk = self.compile_insn(insn, state)
                if chunk is not None:
                    data += chunk
                    if isinstance(chunk, BaseDeferred):
                        addr += chunk.len()
                    else:
                        addr += len(chunk)

            elif isinstance(insn, Label):
                if context == "repeat":
                    if not hasattr(insn, "label_error_emitted"):
                        reports.error(
                            "unexpected-symbol-definition",
                            (insn.ctx_start, insn.ctx_end, "Labels cannot be defined inside '.repeat' loop")
                        )
                        insn.label_error_emitted = True
                    _ = 1  # for code coverage
                    continue

                self.compile_label(insn, addr, local_symbols)
                if not insn.local:
                    local_symbols = CaseInsensitiveDict()

            elif isinstance(insn, Assignment):
                if context == "repeat":
                    if not hasattr(insn, "assignment_error_emitted"):
                        reports.error(
                            "unexpected-symbol-definition",
                            (insn.ctx_start, insn.ctx_end, "Variables cannot be defined inside '.repeat' loop")
                        )
                        insn.assignment_error_emitted = True
                    _ = 1  # for code coverage
                    continue

                self.compile_assignment(insn)

            else:
                assert False  # pragma: no cover

        return data


    def compile_label(self, label, addr, local_symbols):
        if label.local:
            if label.name in local_symbols:
                prev_sym, _ = local_symbols[label.name]
                reports.error(
                    "duplicate-symbol",
                    (label.ctx_start, label.ctx_end, f"Duplicate local label '{label.name}:'"),
                    (prev_sym.ctx_start, prev_sym.ctx_end, "A symbol with the same name has been already declared here")
                )
            local_symbols[label.name] = (label, addr)
        else:
            if label.name in self.symbols:
                prev_sym, _ = self.symbols[label.name]
                reports.error(
                    "duplicate-symbol",
                    (label.ctx_start, label.ctx_end, f"Duplicate symbol '{label.name}'"),
                    (prev_sym.ctx_start, prev_sym.ctx_end, "A symbol with the same name has been already declared here")
                )
            self.symbols[label.name] = (label, addr)


    def compile_assignment(self, var):
        var.symbol_value = None
        if var.name.name in self.symbols:
            prev_sym, _ = self.symbols[var.name.name]
            reports.error(
                "duplicate-symbol",
                (var.ctx_start, var.ctx_end, f"Duplicate variable '{var.name.name}'"),
                (prev_sym.ctx_start, prev_sym.ctx_end, "A symbol with the same name has been already declared here")
            )
        else:
            self.symbols[var.name.name] = (var, None)


    def compile_insn(self, insn, state):
        if insn.name.name in builtins:
            return builtins[insn.name.name].compile(state, self, insn)
        elif "." + insn.name.name in builtins:
            reports.warning(
                "meta-typo",
                (insn.name.ctx_start, insn.name.ctx_end, f"'{insn.name.name}' is not a metacommand by itself, but '.{insn.name.name}' is.\nPlease be explicit and add a dot."),
            )
            return builtins["." + insn.name.name].compile(state, self, insn)
        elif insn.name.name in self.symbols:
            # Resolve a macro
            symbol, _ = self.symbols[insn.name.name]
            # TODO: pdpy in Macro-11 compatibility mode should support implicit
            # .word directive. That is when 'x = 5; x' is the same as
            # 'x = 5; .word x'. This is probably the right place to add the
            # check.
            if isinstance(symbol, Label):
                reports.error(
                    "meta-type-mismatch",
                    (insn.name.ctx_start, insn.name.ctx_end, f"'{insn.name.name}' is used as an instruction name"),
                    (symbol.ctx_start, symbol.ctx_end, "...but is defined as a label here. " + reports.terminal_link("Are you looking for macros?", "https://pdpy.github.io/macros"))
                )
                return None
            elif isinstance(symbol, Assignment):
                reports.error(
                    "meta-type-mismatch",
                    (insn.name.ctx_start, insn.name.ctx_end, f"'{insn.name.name}' is used as an instruction name"),
                    (symbol.ctx_start, symbol.ctx_end, "...but is defined as a constant here. " + reports.terminal_link("You may be looking for MACRO-11 macros.", "https://pdpy.github.io/macros") + "\nNote that macros can also be defined implicitly using syntax like 'macro_name = .word 123'. Did you make a typo?")
                )
                return None
            else:
                # TODO: macros
                assert False  # pragma: no cover
        else:
            reports.error(
                "unknown-insn",
                (insn.name.ctx_start, insn.name.ctx_end, f"'{insn.name.name}' is an undefined {'metainstruction' if insn.name.name[0] == '.' else 'instruction'}.\nIs our database incomplete? " + reports.terminal_link("Report that on GitHub.", "https://github.com/imachug/pdpy11/issues/new"))
            )
            return None


    def add_files(self, files_ast):
        self.files += files_ast

        for file_ast in files_ast:
            data = self.compile_file(file_ast, self.cur_emit_location)
            self.generated_code += data
            if isinstance(data, BaseDeferred):
                self.cur_emit_location += data.len()
            else:
                self.cur_emit_location += len(data)


    def link(self):
        if not self.link_base.settled:
            self.link_base.settle(0o1000)  # TODO: maybe report a warning?

        code = wait(self.generated_code)
        return (wait(self.link_base), code)
