from mutmut.__main__ import climain
import subprocess
import sys


original_popen = subprocess.Popen

def popen(cmd, *args, **kwargs):
    if cmd[0] == "python":
        cmd = [sys.executable] + cmd[1:]
    return original_popen(cmd, *args, **kwargs)

subprocess.Popen = popen

sys.path.insert(1, "tests")


if __name__ == "__main__":
    climain()
