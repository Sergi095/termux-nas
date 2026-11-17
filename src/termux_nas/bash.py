"""Bash hooks: local commands pass through; selected NAS paths use the bridge."""

RCFILE = r'''
if [ -f "$HOME/.bashrc" ]; then source "$HOME/.bashrc"; fi

_nas_normalize() {
    command nas _normalize "$PWD" "$1"
}

_nas_is_remote() {
    case "$1" in
        "$TERMUX_NAS_MOUNT"|"$TERMUX_NAS_MOUNT"/*) return 0 ;;
        *) return 1 ;;
    esac
}

cd() {
    if [ "$#" -eq 0 ] || [ "$1" = "-" ]; then builtin cd "$@"; return; fi
    if [ "$#" -ne 1 ]; then builtin cd "$@"; return; fi
    local target
    target="$(_nas_normalize "$1")" || return
    if _nas_is_remote "$target"; then
        command nas _isdir "$target" || { printf 'nas: not a NAS directory: %s\n' "$target" >&2; return 1; }
        command mkdir -p -- "$target" || return
        builtin cd -- "$target"
    else
        builtin cd "$@"
    fi
}

ls() {
    local target="$PWD" arg count=0 flags=""
    for arg in "$@"; do
        case "$arg" in
            --) ;;
            -*) flags="${flags}${arg#-}" ;;
            *) target="$(_nas_normalize "$arg")" || return; count=$((count + 1));;
        esac
    done
    if _nas_is_remote "$target"; then
        if [ "$count" -gt 1 ]; then
            printf 'nas: remote ls currently accepts one path\n' >&2; return 2
        fi
        command nas _ls "$target" "$flags"
    else
        command ls "$@"
    fi
}

cat() {
    if [ "$#" -eq 1 ]; then
        local target
        target="$(_nas_normalize "$1")" || return
        if _nas_is_remote "$target"; then command nas _cat "$target"; return; fi
    fi
    command cat "$@"
}

cp() {
    if [ "$#" -eq 2 ]; then
        local source destination
        source="$(_nas_normalize "$1")" || return
        destination="$(_nas_normalize "$2")" || return
        if _nas_is_remote "$source" || _nas_is_remote "$destination"; then
            command nas _cp "$source" "$destination"; return
        fi
    fi
    command cp "$@"
}

printf 'NAS available at %s. Local Termux files remain available.\n' "$TERMUX_NAS_MOUNT"
'''
