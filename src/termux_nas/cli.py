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
    add.add_argument("--share", help="One SMB share; omit to show all accessible shares")
    add.add_argument("--user", required=True)
    add.add_argument("--port", type=int, default=445)
    add.add_argument("--mount-name", default="nas", help="Folder name under your Termux home (default: nas)")
    sub.add_parser("list", help="List saved NAS connections")
    set_mount = sub.add_parser("set-mount", help="Set a folder name or path for a saved connection")
    set_mount.add_argument("name")
    set_mount.add_argument("folder")
    shell = sub.add_parser("shell", help="Open Bash with local files and a NAS folder")
    shell.add_argument("name", nargs="?")
    mount = sub.add_parser("mount", help="Open a PRoot shell with a NAS folder that syncs changes to SMB")
    mount.add_argument("name", nargs="?")
    mount.add_argument("--at", metavar="FOLDER", help="Use this empty folder as the NAS path for this session")
    mount.add_argument("--proot", help="Path to the patched PRoot binary")
    remove = sub.add_parser("remove", help="Forget a saved NAS connection")
    remove.add_argument("name")
    return p


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "_sync":
        from .hydrate import request_sync

        try:
            if len(argv) != 2:
                raise ValueError("Usage: nas _sync SOCKET")
            request_sync(argv[1])
            return 0
        except (OSError, ValueError) as error:
            print(f"nas: sync failed: {error}", file=sys.stderr)
            return 1
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
                target = item.get("mount_path") or f"~/{item.get('mount_name', 'nas')}"
                share = item.get("share") or "*"
                print(f"{name}: //{item['host']}/{share} ({item['user']}) -> {target}")
        elif args.command == "set-mount":
            if args.name not in connections:
                raise ValueError(f"Unknown connection: {args.name}")
            if "/" in args.folder or args.folder.startswith("~"):
                target = config.normalize_mount_path(args.folder)
                connections[args.name]["mount_path"] = target
            else:
                config.validate_mount_name(args.folder)
                target = f"~/{args.folder}"
                connections[args.name]["mount_name"] = args.folder
                connections[args.name].pop("mount_path", None)
            config.save(connections)
            print(f"{args.name} will appear at {target}")
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
            from .smb import SMBAllSharesBackend, SMBBackend
            item = connections[name]
            password = getpass.getpass(f"SMB password for {item['user']}@{item['host']}: ")
            share = item.get("share")
            backend = (SMBBackend(str(item["host"]), str(share), str(item["user"]), password, int(item["port"]))
                       if share else SMBAllSharesBackend(str(item["host"]), str(item["user"]), password, int(item["port"])))
            if not backend.is_dir(""):
                raise ValueError("SMB share is not a directory")
            if args.command == "shell":
                from .session import run_shell

                return run_shell(backend, str(item.get("mount_name", "nas")))
            from .mounted import run_mounted_shell

            mount_path = args.at if args.at is not None else item.get("mount_path")
            return run_mounted_shell(backend, str(item.get("mount_name", "nas")), args.proot,
                                     mount_path=str(mount_path) if mount_path is not None else None)
        return 0
    except (OSError, ValueError, KeyError, ImportError) as error:
        print(f"nas: {error}", file=sys.stderr)
        return 1


def mount_main() -> int:
    return main(["mount", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
