"""Command line entry point."""

import argparse
import getpass
import sys

from . import config


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nas", description="Browse SMB shares in a rootless Termux shell")
    sub = p.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="Save NAS connection details")
    add.add_argument("name")
    add.add_argument("--host", required=True)
    add.add_argument("--share", required=True)
    add.add_argument("--user", required=True)
    add.add_argument("--port", type=int, default=445)
    sub.add_parser("list", help="List saved NAS connections")
    shell = sub.add_parser("shell", help="Open an interactive NAS browser")
    shell.add_argument("name", nargs="?")
    remove = sub.add_parser("remove", help="Forget a saved NAS connection")
    remove.add_argument("name")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        connections = config.load()
        if args.command == "add":
            config.validate(args.name, args.host, args.share, args.user, args.port)
            connections[args.name] = {"host": args.host, "share": args.share, "user": args.user, "port": args.port}
            config.save(connections)
            print(f"Saved {args.name}. Password will be requested when you connect.")
        elif args.command == "list":
            for name, item in sorted(connections.items()):
                print(f"{name}: //{item['host']}/{item['share']} ({item['user']})")
        elif args.command == "remove":
            if args.name not in connections:
                raise ValueError(f"Unknown connection: {args.name}")
            del connections[args.name]
            config.save(connections)
        elif args.command == "shell":
            name = args.name
            if name is None:
                if len(connections) != 1:
                    raise ValueError("Specify a connection name (see nas list)")
                name = next(iter(connections))
            if name not in connections:
                raise ValueError(f"Unknown connection: {name}")
            from .smb import SMBBackend
            from .shell import NASShell

            item = connections[name]
            password = getpass.getpass(f"SMB password for {item['user']}@{item['host']}: ")
            backend = SMBBackend(str(item["host"]), str(item["share"]), str(item["user"]), password, int(item["port"]))
            if not backend.is_dir(""):
                raise ValueError("SMB share is not a directory")
            NASShell(backend).run()
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"nas: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
