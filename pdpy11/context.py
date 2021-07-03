class Context:
    def __init__(self, filename, code):
        self.filename = filename
        self.code = code
        self.pos = 0


    def save(self):
        ctx = Context(self.filename, self.code)
        ctx.pos = self.pos
        return ctx


    def restore(self, ctx):
        self.pos = ctx.pos


    def skip_whitespace(self):
        while self.pos < len(self.code):
            if self.code[self.pos].strip() == "":
                self.pos += 1
            elif self.code[self.pos] == ";":
                self.pos = self.code.find("\n", self.pos)
                if self.pos == -1:
                    self.pos = len(self.code)
            else:
                _ = 1  # For code coverage. CPython optimizes 'break' away otherwise
                break


    def eof(self):
        copy = self.save()
        copy.skip_whitespace()
        return copy.code[copy.pos:].strip() == ""


    def __repr__(self):
        line_no = self.code[:self.pos].count("\n")
        idx_line_start = self.code.rfind("\n", 0, self.pos) + 1
        col_no = (self.pos - idx_line_start) + self.code[idx_line_start:self.pos].count("\t") * 3
        return f"{self.filename}:{line_no + 1}:{col_no + 1}"
