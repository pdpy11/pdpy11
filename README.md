# PDPy11

PDPy11 is a cross-platform assembler for PDP-11 computers.


## Requirements

- Python 3.6 or later
- No Python modules required
- Any platform (Windows, Mac OS, Linux)


## Installation

Use pip.

```shell
$ pip3 install pdpy11
```

(some modern systems use `pip` instead of `pip3` for Python 3 packages)


## Licensing

PDPy11 is licensed under GNU General Public License version 3 (which is attached to PDPy11 in 'LICENSE' file), or (at your opinion) any later version.


## Development

Install the following packages from pip: `coverage pytest mutmut pyfakefs pylint`. You can now run tests using `make test`, run tests with coverage using `make cov`, run mutation tests using `make mut` and run linter using `make lint`. You can add `PYTHON=...` option to set path to or name of Python interpreter.
