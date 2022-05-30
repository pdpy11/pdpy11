from .containers import CaseInsensitiveDict
from .insns import instructions
from . import metacommands as _  # has side effects
from .metacommand_impl import metacommands


builtin_commands = CaseInsensitiveDict(instructions)
for name, command in metacommands.items():
    builtin_commands[name] = command
