from contextlib import contextmanager

from pdp import reports


@contextmanager
def expect_warning(*warnings):
    matched_warnings = []

    def report_handler(priority, identifier, *lst_reports):
        if priority != reports.warning:
            raise Exception(identifier)  # pragma: no cover
        matched_warnings.append(identifier)

    with reports.handle_reports(report_handler):
        yield

    assert sorted(matched_warnings) == sorted(warnings)


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

    assert sorted(matched_errors) == sorted(errors)
    assert is_error_condition


@contextmanager
def expect_no_warnings():
    def report_handler(priority, identifier, *lst_reports):
        raise Exception(identifier)  # pragma: no cover

    with reports.handle_reports(report_handler):
        yield
