from contextlib import contextmanager

from pdpy11 import reports


@contextmanager
def expect_warning(*warnings):
    matched_warnings = []

    def report_handler(priority, identifier, *lst_reports):
        if priority != reports.warning:
            raise Exception(identifier)  # pragma: no cover
        matched_warnings.append(identifier)

    with reports.handle_reports(report_handler):
        yield

    matched_warnings = sorted(matched_warnings)
    warnings = sorted(warnings)
    assert matched_warnings == warnings, f"{matched_warnings} != {warnings}"


@contextmanager
def expect_error(*errors):
    matched_errors = []
    is_error_condition = False

    def report_handler(priority, identifier, *lst_reports):
        nonlocal is_error_condition
        if priority is not reports.warning:
            is_error_condition = True
        matched_errors.append(identifier)

    try:
        with reports.handle_reports(report_handler):
            yield
    except reports.UnrecoverableError:
        pass
    else:
        assert False, "Should raise an error (critical or not)"  # pragma: no cover

    assert is_error_condition

    matched_errors = sorted(matched_errors)
    errors = sorted(errors)
    assert matched_errors == errors, f"{matched_errors} != {errors}"
