"""Paths displayed by the NAS shell are virtual, not OS mount points."""

import posixpath


VIRTUAL_ROOT = "~/nas"


def resolve(current: str, requested: str) -> str:
    """Return a share-relative path, clamped to the share root."""
    if not requested or requested == VIRTUAL_ROOT:
        return ""
    if requested.startswith(VIRTUAL_ROOT + "/"):
        raw = requested[len(VIRTUAL_ROOT) + 1 :]
    elif requested.startswith("/") or requested.startswith("~"):
        raise ValueError("Use ~/nas or a path relative to the current NAS directory")
    else:
        raw = posixpath.join(current, requested)

    parts: list[str] = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        if "\\" in part or "\x00" in part:
            raise ValueError("Invalid NAS path")
        parts.append(part)
    return "/".join(parts)


def display(path: str) -> str:
    return VIRTUAL_ROOT + ("/" + path if path else "")
