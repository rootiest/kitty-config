# Copyright (C) 2026 Rootiest
# SPDX-License-Identifier: AGPL-3.0-or-later

# Sourced via `fish -C "source -- ~/.config/kitty/restore-paused.fish <cmd>"`
# when kitty restores a tab whose active command was not on the auto-run
# allowlist. Stores the command in $KITTY_PAUSED_COMMAND, prints a review
# notice, and defines the one-shot `restore-paused` function for that shell.

#   ────────────────────────── Helper: palette ──────────────────────────
# Uses fish-config's shared __fish_palette when loaded; falls back to matching
# roles (still honoring NO_COLOR) when kitty-config is used with stock fish.
function __kitty_restore_paused_palette --no-scope-shadowing
    if functions -q __fish_palette
        __fish_palette
        return 0
    end
    if test -n "$NO_COLOR"
        for __role in c_reset c_cmd c_flag c_arg c_dim c_head c_warn c_err c_ok
            set $__role ''
        end
        return 0
    end
    set c_reset (set_color normal)
    set c_cmd (set_color brblue)
    set c_flag (set_color brgreen)
    set c_arg (set_color cyan)
    set c_dim (set_color brblack)
    set c_head (set_color --bold cyan)
    set c_warn (set_color yellow)
    set c_err (set_color red)
    set c_ok (set_color green)
    return 0
end

#   ─────────────────────── User-facing command ─────────────────────────
# DEPENDENCIES
#   __fish_palette (optional)
#
# SYNOPSIS
#   restore-paused [-c | --clear] [-h | --help]
#
# DESCRIPTION
#   Runs the paused command stored in $KITTY_PAUSED_COMMAND by kitty's
#   session-autosave watcher, then clears the variable, removes the kitty
#   `kitty_paused_cmd` user variable, and erases itself from the current
#   shell. Allows running other commands or inspecting/editing
#   $KITTY_PAUSED_COMMAND before executing it.
#
# ARGUMENTS
#   -c, --clear  Dismiss and clear the paused command without running it
#   -h, --help   Show this help message
#
# EXIT STATUS
#   0  Command succeeded, was cleared, or help was shown
#   1  No paused command is set in $KITTY_PAUSED_COMMAND
#   2  Invalid option or unexpected argument
#   *  Exit status of the restored command
#
# EXAMPLE
#   restore-paused
#   restore-paused --clear
#
# NOTES
#   Defined only in restored kitty tabs that had a non-allowlisted command
#   running at close or reboot. Erases itself after running or clearing.
function restore-paused --description 'Run or clear the paused command saved before kitty closed'
    __kitty_restore_paused_palette

    argparse -n restore-paused 'h/help' 'c/clear' -- $argv
    or return

    if set -q _flag_help
        echo "$c_head""Usage:$c_reset $c_cmd""restore-paused$c_reset $c_flag""[-c|--clear]$c_reset $c_flag""[-h|--help]$c_reset"
        echo
        echo "  Run or dismiss the paused command stored in \$KITTY_PAUSED_COMMAND."
        echo
        echo "$c_head""Options:$c_reset"
        echo "  $c_flag""-c, --clear$c_reset  Dismiss and clear the paused command without running it"
        echo "  $c_flag""-h, --help$c_reset   Show this help message"
        return 0
    end

    if test (count $argv) -gt 0
        echo "$c_err""restore-paused: unexpected arguments: $argv$c_reset" >&2
        return 2
    end

    if set -q _flag_clear
        set -e KITTY_PAUSED_COMMAND
        functions -e restore-paused __kitty_restore_paused_palette
        if test "$TERM" = xterm-kitty
            printf '\e]1337;SetUserVar=kitty_paused_cmd\a'
        end
        echo "$c_dim""Cleared paused command.$c_reset"
        return 0
    end

    if not set -q KITTY_PAUSED_COMMAND; or test -z "$KITTY_PAUSED_COMMAND"
        echo "$c_err""restore-paused: no paused command to restore$c_reset" >&2
        return 1
    end

    set -l _cmd "$KITTY_PAUSED_COMMAND"
    set -e KITTY_PAUSED_COMMAND
    functions -e restore-paused __kitty_restore_paused_palette
    if test "$TERM" = xterm-kitty
        printf '\e]1337;SetUserVar=kitty_paused_cmd\a'
    end

    # Record the actual command in fish history for recall later
    builtin history append -- "$_cmd" 2>/dev/null

    echo "$c_ok""▶$c_reset $_cmd"
    eval "$_cmd"
end

#   ──────────────────────── Startup initialization ─────────────────────
function __kitty_restore_paused_init
    if test (count $argv) -eq 0; or test -z "$argv[1]"
        return 0
    end

    __kitty_restore_paused_palette
    set -gx KITTY_PAUSED_COMMAND "$argv[1]"

    # Mirror into kitty user_vars so another close/reboot before running
    # `restore-paused` keeps the command pending.
    if test "$TERM" = xterm-kitty; and type -q base64
        set -l _b64 (string join '' -- (printf '%s' "$KITTY_PAUSED_COMMAND" | command base64))
        printf '\e]1337;SetUserVar=kitty_paused_cmd=%s\a' "$_b64"
    end

    echo "$c_warn""⏸ Paused command (not auto-run):$c_reset"
    echo "  $KITTY_PAUSED_COMMAND"
    echo "$c_dim""Run $c_cmd""restore-paused$c_dim when ready, or $c_cmd""restore-paused$c_dim $c_flag""--clear$c_dim to dismiss ($c_arg\$KITTY_PAUSED_COMMAND$c_dim).$c_reset"
    return 0
end

__kitty_restore_paused_init $argv
functions -e __kitty_restore_paused_init
