from dataclasses import dataclass
import itertools
import re


class Report:
    def __init__(self, text: str):
        self.text: str = text

    def __call__(self, *args, **kwargs):
        emit_report(self, *args, **kwargs)

error = Report("\x1b[91mError\x1b[0m")
critical = Report("\x1b[91mError\x1b[0m")
warning = Report("\x1b[33mWarning\x1b[0m")


@dataclass
class ReportInfo:
    line_no: int
    start_col_no: int
    end_col_no: int
    text: str
    closing_line_no: int = None
    max_column: int = -1


def colorize(text):
    # TODO: better replacements
    text = text.replace("\x00", "␀").replace("\x01", "").replace("\x02", "")
    if ";" in text:
        text, comment = text[:text.index(";")], text[text.index(";"):]
    else:
        comment = None
    text = re.sub(r"(\b[a-zA-Z_]+\b)", "\x01\x1b[94m\x02\\1\x01\x1b[39m\x02", text)
    text = re.sub(r"\b(r[0-7]|sp|pc)\b", "\x01\x1b[93m\x02\\1\x01\x1b[39m\x02", text, flags=re.I)
    text = re.sub(r"(\b(0[xX][0-9a-fA-F]+|0o[0-7]+|\d+\.?)\b)", "\x01\x1b[95m\x02\\1\x01\x1b[39m\x02", text)
    if comment:
        text += f"\x01\x1b[38;5;242m\x02{comment}\x01\x1b[39m\x02"
    return text


class handle_reports:
    handlers_stack = []

    def __init__(self, fn):
        self.fn = fn
        self.obj = None
        self.is_error_condition = False

    def __enter__(self):
        if hasattr(self.fn, "__enter__"):
            self.obj = self.fn.__enter__()
        else:
            self.obj = self.fn

        self.handlers_stack.append(self)

        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        assert self.handlers_stack.pop() is self

        if hasattr(self.obj, "__exit__"):
            return self.obj.__exit__(exc_type, exc_value, exc_tb)

        if exc_type is not UnrecoverableError and self.is_error_condition:
            raise UnrecoverableError()

        return False


class TextHandler:
    def __enter__(self):
        return self


    def __exit__(self, exc_type, exc_value, exc_tb):
        pass


    def __call__(self, priority, identifier, *reports):
        for file_i, (filename, file_reports) in enumerate(itertools.groupby(reports, key=lambda report: report[0].filename)):
            file_reports = list(file_reports)
            ctx = file_reports[0][0]
            lines = ctx.code.split("\n")

            if file_i == 0:
                print(f"{priority.text} in \x1b[96m{filename}\x1b[0m: \x1b[38;5;208m[-W{identifier}]\x1b[0m")
            else:
                print(f"In \x1b[96m{filename}\x1b[0m:")

            reports_lst = []
            for ctx_start, ctx_end, text in file_reports:
                assert ctx_start.filename == ctx_end.filename
                idx_line_start = ctx_start.code.rfind("\n", 0, ctx_start.pos) + 1
                line_no = ctx_start.code[:idx_line_start].count("\n")
                start_col_no = (ctx_start.pos - idx_line_start) + ctx_start.code[idx_line_start:ctx_start.pos].count("\t") * 3

                if "\n" in ctx.code[ctx_start.pos:ctx_end.pos]:
                    # Hotfix: terminate at EOL. TODO: allow multiline reports
                    end_col_no = len(lines[line_no])
                else:
                    end_col_no = start_col_no + (ctx_end.pos - ctx_start.pos)

                reports_lst.append(ReportInfo(line_no, start_col_no, end_col_no, text))

            min_line_no = max(min(report.line_no for report in reports_lst) - 2, 0)
            max_line_no = min(max(report.line_no for report in reports_lst) + 3, len(lines))

            events_per_line = {line_no: [] for line_no in range(min_line_no, max_line_no)}
            previous_line_no = -1
            for i, report in enumerate(reports_lst):
                if report.line_no < previous_line_no:
                    report.closing_line_no = previous_line_no
                    events_per_line[report.line_no].append((1, report))
                    for line_no in range(report.line_no + 1, previous_line_no):
                        events_per_line[line_no].append((0, report))
                    events_per_line[previous_line_no].append((-1, report))
                else:
                    previous_line_no = report.line_no
                    events_per_line[previous_line_no].append((2, report))

            open_reports = []
            cnt_columns = 0
            for line_no, events in events_per_line.items():
                events.sort(key=lambda event: event[0])
                events.reverse()
                for event, report in events:
                    if event == 1:
                        report.max_column = 0
                        open_reports.append(report)
                        for i, open_report in enumerate(open_reports):
                            open_report.max_column = len(open_reports) - i - 1
                        cnt_columns = max(cnt_columns, len(open_reports))
                    elif event == -1:
                        open_reports.remove(report)

            for line_no, events in events_per_line.items():
                events.sort(key=lambda event: event[0])
                events.reverse()
                print("\x1b[92m" + str(line_no + 1).rjust(5) + "\x1b[0m \x1b[38;5;242m│ ", end="")

                chars = ["  "] * cnt_columns
                has_report = False
                for event, report in events:
                    i = cnt_columns - 1 - report.max_column
                    if event == 1:
                        chars[i] = "┌ "
                    elif event in (0, -1):
                        chars[i] = "│ "
                    has_report = has_report or event in (1, 2)
                print("\x1b[38;5;11m" + "".join(chars) + "\x1b[0m", end="")

                line = lines[line_no].replace("\t", " " * 4)
                if has_report:
                    print("\x1b[0m" + colorize(line), end="")
                else:
                    print("\x1b[38;5;242m" + line + "\x1b[0m", end="")

                for event, report in events:
                    if event in (1, 2):
                        print(f"\x1b[{1 + 5 + 3 + 2 * cnt_columns + report.start_col_no}G\x1b[48;5;52m{colorize(line[report.start_col_no:report.end_col_no])}\x1b[0m", end="")

                print()

                for event, report in events:
                    i = cnt_columns - 1 - report.max_column
                    if event == 1:
                        chars[i] = "│ "

                for event, report in events:
                    i = cnt_columns - 1 - report.max_column
                    if event == -1:
                        chars[i] = "└ "
                        old_chars = chars[:]
                        for j in range(i, cnt_columns):
                            if chars[j][0] == "│":
                                chars[j] = "┼─"
                            elif chars[j][0] == " ":
                                chars[j] = "──"
                            else:
                                chars[j] = chars[j][0] + "─"
                        for line_i, line in enumerate(report.text.split("\n")):
                            print(" " * 5 + " \x1b[38;5;242m│ \x1b[38;5;11m" + "".join(chars) + ("─" if line_i == 0 else " ") * (report.start_col_no - 2) + "─ " + line + "\x1b[0m")
                            if line_i == 0:
                                chars = old_chars
                                chars[i] = "  "
                    elif event == 2:
                        for line_i, line in enumerate(report.text.split("\n")):
                            print(" " * 5 + " \x1b[38;5;242m│ \x1b[38;5;11m" + "".join(chars) + " " * report.start_col_no + ("🡹 " if line_i == 0 else "  ") + line + "\x1b[0m")

        print()


def terminal_link(text, href):
    return "\x1b]8;;" + href + "\x1b\\" + text + "\x1b]8;;\x1b\\"


def emit_report(priority, identifier, *reports):
    if not handle_reports.handlers_stack:
        # Shouldn't happen
        raise Exception("No report handlers are set")  # pragma: no cover

    handler = handle_reports.handlers_stack[-1]
    handler.obj(priority, identifier, *reports)

    if priority in (error, critical):
        handler.is_error_condition = True

    if priority is critical:
        raise UnrecoverableError()


class RecoverableError(Exception):
    pass

class UnrecoverableError(Exception):
    pass
