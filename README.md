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

On Windows, installing via pip works too, but pay attention to any warnings. If pip says anything along the lines of `The script pdpy11.exe is installed in '...' which is not on PATH`, add the path pip mentions to the PATH variable. On newer Windows, this can be done by searching for 'Edit the system environment variables' in the Start menu and clicking through 'Environment Variables...', then 'User variables for ...' or 'System variables' depending on whether you want to install the compiler for a single user or globally, followed by 'Path', and adding the path to the end of the list.

If you're using Sublime Text, you might also want to install various utilities for syntax highlighting and building [here](https://github.com/pdpy11/sublime-plugin).


## Licensing

PDPy11 is licensed under GNU General Public License version 3 (which is attached to PDPy11 in 'LICENSE' file), or (at your option) any later version.


## Development

Install the following packages from pip: `coverage pytest mutmut pyfakefs pylint`. You can now run tests using `make test`, run tests with coverage using `make cov`, run mutation tests using `make mut` and run linter using `make lint`. You can add `PYTHON=...` option to set path to or name of Python interpreter.
