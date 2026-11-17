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
    add.add_argument("--mount-name", default="nas", help="Folder name under your Termux home (default: nas)")
    sub.add_parser("list", help="List saved NAS connections")
    set_mount = sub.add_parser("set-mount", help="Change the folder name for a saved connection")
    set_mount.add_argument("name")
    set_mount.add_argument("folder")
    shell = sub.add_parser("shell", help="Open Bash with local files and a NAS folder")
    shell.add_argument("name", nargs="?")
    mount = sub.add_parser("mount", help="Open a PRoot shell with a read-only NAS filesystem")
    mount.add_argument("name", nargs="?")
    mount.add_argument("--proot", help="Path to the patched PRoot binary")
    remove = sub.add_parser("remove", help="Forget a saved NAS connection")
    remove.add_argument("name")
    return p


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0].startswith("_"):
        from .bridge import helper

        try:
            return helper(argv)
        except (OSError, ValueError, KeyError) as error:
            print(f"nas: {error}", file=sys.stderr)
            return 1
    args = parser().parse_args(argv)
    try:
        connections = config.load()
        if args.command == "add":
            config.validate(args.name, args.host, args.share, args.user, args.port, args.mount_name)
            connections[args.name] = {"host": args.host, "share": args.share, "user": args.user, "port": args.port, "mount_name": args.mount_name}
            config.save(connections)
            print(f"Saved {args.name}. Password will be requested when you connect.")
        elif args.command == "list":
            for name, item in sorted(connections.items()):
                print(f"{name}: //{item['host']}/{item['share']} ({item['user']}) -> ~/{item.get('mount_name', 'nas')}")
        elif args.command == "set-mount":
            if args.name not in connections:
                raise ValueError(f"Unknown connection: {args.name}")
            config.validate_mount_name(args.folder)
            connections[args.name]["mount_name"] = args.folder
            config.save(connections)
            print(f"{args.name} will appear at ~/{args.folder}")
        elif args.command == "remove":
            if args.name not in connections:
                raise ValueError(f"Unknown connection: {args.name}")
            del connections[args.name]
            config.save(connections)
        elif args.command in ("shell", "mount"):
            name = args.name
            if name is None:
                if len(connections) != 1:
                    raise ValueError("Specify a connection name (see nas list)")
                name = next(iter(connections))
            if name not in connections:
                raise ValueError(f"Unknown connection: {name}")
            from .smb import SMBBackend
            item = connections[name]
            password = getpass.getpass(f"SMB password for {item['user']}@{item['host']}: ")
            backend = SMBBackend(str(item["host"]), str(item["share"]), str(item["user"]), password, int(item["port"]))
            if not backend.is_dir(""):
                raise ValueError("SMB share is not a directory")
            if args.command == "shell":
                from .session import run_shell

                return run_shell(backend, str(item.get("mount_name", "nas")))
            from .mounted import run_mounted_shell

            return run_mounted_shell(backend, str(item.get("mount_name", "nas")), args.proot)
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"nas: {error}", file=sys.stderr)
        return 1


def mount_main() -> int:
    return main(["mount", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
