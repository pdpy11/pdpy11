from .builtins import builtins
from .containers import CaseInsensitiveDict
from .deferred import Promise, NotReadyError
from .types import Instruction, Label, Assignment
from . import reports


class Compiler:
    def __init__(self):
        self.symbols = CaseInsensitiveDict()
        self.local_symbols = CaseInsensitiveDict()
        self.files_by_filename = {}
        self.link_base = Promise("LA")
        self.current_emit_address = self.link_base


    def add_label(self, label):
        if label.local:
            if label.name in self.local_symbols:
                prev_sym = self.local_symbols[label.name]
                reports.error(
                    (label.ctx_start, label.ctx_end, f"Duplicate local label '{label.name}:'"),
                    (prev_sym.ctx_start, prev_sym.ctx_end, "A symbol with the same name has been already declared here")
                )

            self.local_symbols[label.name] = label
        else:
            if label.name in self.symbols:
                prev_sym = self.symbols[label.name]
                reports.error(
                    (label.ctx_start, label.ctx_end, f"Duplicate symbol '{label.name}'"),
                    (prev_sym.ctx_start, prev_sym.ctx_end, "A symbol with the same name has been already declared here")
                )

            self.symbols[label.name] = label
            self.local_symbols = {}


    def add_variable(self, var):
        if var.name in self.symbols:
            prev_sym = self.symbols[var.name]
            reports.error(
                (var.ctx_start, var.ctx_end, f"Duplicate variable '{var.name}'"),
                (prev_sym.ctx_start, prev_sym.ctx_end, "A symbol with the same name has been already declared here")
            )
        else:
            self.symbols[var.name] = var


    def scan_symbols(self, file):
        self.files_by_filename[file.filename] = file

        prev_local_symbols = self.local_symbols
        self.local_symbols = {}

        try:
            for insn in file.body.insns:
                if isinstance(insn, Label):
                    self.add_label(insn)
                elif isinstance(insn, Assignment):
                    self.add_variable(insn)
                insn.local_symbols = self.local_symbols
        finally:
            self.local_symbols = prev_local_symbols


    def compile_file(self, file):
        for insn in file.body.insns:
            if isinstance(insn, Instruction) and insn.name.name.lower() in (".end", "end"):
                break
            self.compile_insn(insn)


    def compile_insn(self, insn):
        insn.emit_address = self.current_emit_address

        if isinstance(insn, Instruction):
            if insn.name.name in self.symbols:
                # Resolve a macro
                symbol = self.symbols[insn.name.name]
                if isinstance(symbol, Label):
                    reports.error(
                        (insn.name.ctx_start, insn.name.ctx_end, f"'{insn.name.name}' is used as an instruction name"),
                        (symbol.ctx_start, symbol.ctx_end, "...but is defined as a label here. " + reports.terminal_link("Are you looking for macros?", "https://pdpy.github.io/macros"))
                    )
                    return
                elif isinstance(symbol, Assignment):
                    reports.error(
                        (insn.name.ctx_start, insn.name.ctx_end, f"'{insn.name.name}' is used as an instruction name"),
                        (symbol.ctx_start, symbol.ctx_end, "...but is defined as a constant here. " + reports.terminal_link("You may be looking for MACRO-11 macros.", "https://pdpy.github.io/macros") + "\nNote that macros can also be defined implicitly using syntax like 'macro_name = .word 123'. Did you make a typo?")
                    )
                    return
                else:
                    # assert isinstance(symbol, Macro)
                    # TODO
                    pass
            elif insn.name.name in builtins:
                chunk = builtins[insn.name.name].substitute(insn)
                if chunk is None:
                    return
                try:
                    chunk_length = len(chunk)
                except NotReadyError:
                    print(insn.name, insn.operands, self.current_emit_address, "???")
                    self.current_emit_address += chunk.len()
                else:
                    print(insn.name, insn.operands, self.current_emit_address, chunk_length)
                    self.current_emit_address += chunk_length
            else:
                reports.error(
                    (insn.name.ctx_start, insn.name.ctx_end, f"'{insn.name.name}' is an undefined instruction.\nIs our database incomplete? " + reports.terminal_link("Report that on GitHub.", "https://github.com/imachug/pdpy11/issues/new"))
                )
                return


def compile_files(files_ast):
    comp = Compiler()

    for file_ast in files_ast:
        comp.scan_symbols(file_ast)

    if reports.is_error_condition():
        raise reports.UnrecoverableError()

    for file_ast in files_ast:
        comp.compile_file(file_ast)

    if reports.is_error_condition():
        raise reports.UnrecoverableError()
