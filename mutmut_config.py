def get_indentation(string):
    return len(string) - len(string.lstrip())


def pre_mutation(context):
    # Skip lines containing report texts
    line_no = context.current_line_index
    cur_indentation = get_indentation(context.source_by_line_number[line_no])
    while line_no > 0:
        line_no -= 1
        line = context.source_by_line_number[line_no]
        indentation = get_indentation(line)
        if indentation < cur_indentation:
            cur_indentation = indentation
            if "reports." in line or "report=(" in line:
                if line_no < context.current_line_index - 1:
                    # Don't skip report identificators
                    context.skip = True
                return
