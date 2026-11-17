"""Interactive virtual NAS directory browser."""

import shlex
import shutil
import sys
from pathlib import Path

from .paths import display, resolve


HELP = "Commands: cd [path], pwd, ls [path], cat file, get remote [local], put local [remote], help, exit"


class NASShell:
    def __init__(self, backend):
        self.backend = backend
        self.cwd = ""

    def execute(self, line: str) -> bool:
        """Execute one command. Return False to leave the shell."""
        try:
            args = shlex.split(line)
        except ValueError as error:
            print(f"nas: {error}", file=sys.stderr)
            return True
        if not args:
            return True
        command, *values = args
        try:
            if command in ("exit", "quit"):
                return False
            if command == "help":
                print(HELP)
            elif command == "pwd":
                self._arity(values, 0, 0)
                print(display(self.cwd))
            elif command == "cd":
                self._arity(values, 0, 1)
                target = resolve(self.cwd, values[0] if values else "~/nas")
                if not self.backend.is_dir(target):
                    raise NotADirectoryError(display(target))
                self.cwd = target
            elif command == "ls":
                self._arity(values, 0, 1)
                target = resolve(self.cwd, values[0] if values else ".")
                for name in self.backend.listdir(target):
                    print(name)
            elif command == "cat":
                self._arity(values, 1, 1)
                with self.backend.read(resolve(self.cwd, values[0])) as source:
                    shutil.copyfileobj(source, sys.stdout.buffer)
            elif command == "get":
                self._arity(values, 1, 2)
                remote = resolve(self.cwd, values[0])
                local = Path(values[1] if len(values) == 2 else Path(remote).name).expanduser()
                with self.backend.read(remote) as source, local.open("xb") as dest:
                    shutil.copyfileobj(source, dest)
                print(f"Saved {local}")
            elif command == "put":
                self._arity(values, 1, 2)
                local = Path(values[0]).expanduser()
                remote = resolve(self.cwd, values[1] if len(values) == 2 else local.name)
                with local.open("rb") as source, self.backend.write(remote) as dest:
                    shutil.copyfileobj(source, dest)
                print(f"Uploaded {display(remote)}")
            else:
                print(f"nas: unknown command: {command}. Type help.", file=sys.stderr)
        except (OSError, ValueError) as error:
            print(f"nas: {error}", file=sys.stderr)
        return True

    @staticmethod
    def _arity(values: list[str], minimum: int, maximum: int) -> None:
        if not minimum <= len(values) <= maximum:
            raise ValueError("Wrong number of arguments. Type help.")

    def run(self) -> None:
        print(HELP)
        while True:
            try:
                line = input(f"{display(self.cwd)} $ ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not self.execute(line):
                break
