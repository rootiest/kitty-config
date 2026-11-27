# Copyright (c) 2026 Rootiest
# SPDX-License-Identifier: AGPL-3.0-or-later

# Keeps kitty's logout snapshot up to date so the session is restored after a
# logout, reboot, or accidentally closing the last kitty window.
#
# kitty saves a snapshot (tabs, splits, working directories, scrollback, window
# geometry) when the desktop portal reports that the session is ending, but
# Plasma never sends that report, and by the time kitty is closed by the
# compositor or killed by systemd its windows are already gone. So this watcher
# saves the same snapshot ahead of time: shortly after tabs, titles or running
# commands change, and every few minutes to refresh the scrollback.
#
# In addition to kitty's built-in state serialization, this watcher:
#   - uses each shell's own working directory rather than the newest child's
#     (so LSP/MCP subprocesses like pyright or gitea-mcp don't hijack `cd`)
#   - auto-restarts strictly safe interactive foreground commands (e.g.
#     `claude` -> `claude --resume`, `agy` -> `agy --continue`, `top`/`btop`)
#     via fish's `--init-command` so config.fish finishes before the command runs
#   - pauses non-allowlisted active commands (e.g. `nvim`, `ssh`, `paru`,
#     pipelines) instead of auto-running them: shows the command on restore,
#     stores it in $KITTY_PAUSED_COMMAND, and provides a one-shot
#     `restore-paused` command to trigger or clear it when ready
#   - rewrites tmux tabs to `tmux-tab.sh attach <session>` so they reattach
#     instead of spawning duplicate sessions
#   - preserves the snapshot on logout/reboot/signal AND when closing the last
#     running kitty instance (while discarding secondary kitty snapshots if
#     another kitty is still open, so new windows never restore stale ones)
#
# Requires restore_session_after_logout yes.

from collections import Counter
import json
import os
import shlex
import subprocess
import time
from typing import Any

from kitty.fast_data_types import add_timer, remove_timer

# Seconds between checks; a save happens at a check when something changed
CHECK_INTERVAL = 5.0
# Seconds after which the snapshot is refreshed even if nothing changed
REFRESH_INTERVAL = 300.0
# Keep the snapshot when the last kitty instance is closed normally, so
# accidentally closing kitty and reopening it restores the session once.
# Secondary kitty instances closed while another kitty is still running still
# discard their snapshot so opening a fresh window does not restore them.
RESTORE_AFTER_NORMAL_QUIT = True
# Processes that run while the desktop session is ending
LOGOUT_PROCESSES = frozenset({'plasma-shutdown', 'ksmserver-logout-greeter', 'systemd-shutdown'})

TMUX_TAB_SCRIPT = os.path.expanduser('~/.config/kitty/tmux-tab.sh')
RESTORE_PAUSED_SCRIPT = os.path.expanduser('~/.config/kitty/restore-paused.fish')
PAUSED_USER_VAR = 'kitty_paused_cmd'
SHELL_NAMES = frozenset({'fish', 'bash', 'zsh', 'sh', 'dash', 'ksh', 'tcsh', 'csh', 'nu'})

# Shell metacharacters that indicate compound/piped/redirected commands.
# Never auto-run; saved as a paused command for manual review instead.
_UNSAFE_SHELL_FRAGMENTS = (';', '&&', '||', '|', '>', '<', '`', '$(', '\n', '\r')

# Strictly safe, idempotent interactive programs that auto-restart immediately
# on restore. Borderline commands (editors with swapfiles, ssh/mosh, cluster
# tools, package managers, one-shot commands, pipelines) are paused instead so
# the user can review and trigger them with `restore-paused`.
RESTORABLE_COMMANDS = frozenset({
    # AI interactive sessions (resumed via _RESUME_DEFAULTS)
    'claude',
    'agy',
    'codex',
    'opencode',
    'gemini',
    # Read-only system monitors
    'top',
    'btop',
    'htop',
    'nvtop',
    'glances',
    'btm',
    'bottom',
    # Read-only TUI viewers, file browsers, and pagers
    'lazygit',
    'tig',
    'gitui',
    'yazi',
    'ranger',
    'lf',
    'ncdu',
    'man',
    'less',
    'ov',
    'bat',
})

# Commands that should neither auto-run nor be offered via `restore-paused`.
_NEVER_RESTORE_COMMANDS = frozenset({'reboot', 'poweroff', 'shutdown', 'halt', 'exit', 'logout'})
_SYSTEMCTL_POWER_ACTIONS = frozenset({'reboot', 'poweroff', 'halt', 'suspend', 'hibernate', 'hybrid-sleep'})

# Commands that should have their interactive resume flag added when invoked
# without an explicit resume/continue/non-interactive flag.
_RESUME_DEFAULTS: dict[str, tuple[str, frozenset[str], frozenset[str]]] = {
    # name -> (flag_to_add, already_resuming_flags, non_interactive_skip_flags)
    'claude': (
        '--resume',
        frozenset({'-r', '--resume', '-c', '--continue', '--from-pr'}),
        frozenset({'-p', '--print', '-h', '--help', '-v', '--version'}),
    ),
    'agy': (
        '--continue',
        frozenset({'-r', '--resume', '-c', '--continue', '--conversation'}),
        frozenset({'-p', '--print', '-h', '--help', '-v', '--version'}),
    ),
}

# Commands whose wrapper function in fish should be called by bare name when
# detected via /proc/<pid>/cmdline (absolute path).
_PREFER_BARE_NAME = frozenset({'claude', 'agy', 'btop', 'top', 'htop', 'nvtop', 'lazygit', 'yazi'})

_state: dict[str, Any] = {'timer': None, 'dirty': True, 'last_save': 0.0, 'stopped': False}


def _desktop_session_ending() -> bool:
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            with open(f'/proc/{pid}/comm') as f:
                if f.read().strip() in LOGOUT_PROCESSES:
                    return True
        except OSError:
            continue
    return False


def _other_live_snapshot_exists(base: str, own_path: str) -> bool:
    from kitty import logout_session as snap

    try:
        with os.scandir(base) as entries:
            for entry in entries:
                if entry.path != own_path and snap.is_saver_running(entry.path):
                    return True
    except FileNotFoundError:
        pass
    return False


def _ppid_of(pid: int) -> int | None:
    try:
        with open(f'/proc/{pid}/stat') as f:
            data = f.read()
        # Format: pid (comm) state ppid ...  (comm may contain spaces/parens)
        rparen = data.rfind(')')
        if rparen == -1:
            return None
        fields = data[rparen + 2 :].split()
        return int(fields[1]) if len(fields) > 1 else None
    except (OSError, ValueError):
        return None


def _is_shell_cmd(cmd: list[str] | tuple[str, ...]) -> bool:
    """True if cmd launches a bare shell or our own `<shell> -C <cmd>` restore."""
    if not cmd:
        return True
    base = os.path.basename(cmd[0]).lstrip('-')
    if base not in SHELL_NAMES:
        return False
    if len(cmd) == 1:
        return True
    if base == 'fish' and len(cmd) == 3 and cmd[1] in ('-C', '--init-command'):
        return True
    return False


def _tmux_client_sessions() -> dict[int, str]:
    """Return {client_pid: session_name} for all attached tmux clients."""
    try:
        out = subprocess.check_output(
            ['tmux', 'list-clients', '-F', '#{client_pid} #{session_name}'],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    result: dict[int, str] = {}
    for line in out.splitlines():
        parts = line.split(' ', 1)
        if len(parts) == 2 and parts[0].isdigit() and parts[1]:
            result[int(parts[0])] = parts[1]
    return result


def _tmux_session_for_window(window: Any, tmux_clients: dict[int, str]) -> str | None:
    if not tmux_clients:
        return None
    pids: list[int] = []
    if window.child.pid is not None:
        pids.append(window.child.pid)
    if window.child.root_pid is not None and window.child.root_pid not in pids:
        pids.append(window.child.root_pid)
    for proc in window.child.foreground_processes:
        p = proc.get('pid')
        if p is not None and p not in pids:
            pids.append(p)
    for pid in pids:
        if pid in tmux_clients:
            return tmux_clients[pid]
    return None


def _is_tmux_launch(cmd: list[str] | tuple[str, ...]) -> bool:
    if not cmd:
        return False
    base = os.path.basename(cmd[0])
    return base in ('tmux-tab.sh', 'tmux')


def _window_cwd(window: Any) -> str:
    """Return the shell/root process's cwd, avoiding LSP/MCP child cwds."""
    from kitty.utils import path_from_osc7_url

    if window.screen.last_reported_cwd and window.at_prompt and not window.child_is_remote:
        if reported := path_from_osc7_url(window.screen.last_reported_cwd):
            return reported
    return (
        window.get_cwd_of_root_child()
        or window.get_cwd_of_child(oldest=True)
        or window.child.cwd
        or ''
    )


def _skip_env_assignments(tokens: list[str]) -> int:
    idx = 0
    while idx < len(tokens) and '=' in tokens[idx] and not tokens[idx].startswith('-'):
        key = tokens[idx].split('=', 1)[0]
        if key and (key[0].isalpha() or key[0] == '_') and all(c.isalnum() or c == '_' for c in key):
            idx += 1
        else:
            break
    return idx


def _is_never_restore(tokens: list[str]) -> bool:
    idx = _skip_env_assignments(tokens)
    if idx >= len(tokens):
        return True
    rest = tokens[idx:]
    prog = os.path.basename(rest[0])
    if prog in ('sudo', 'doas', 'pkexec') and len(rest) > 1:
        # Skip sudo/doas flags to inspect the target command
        j = 1
        while j < len(rest) and rest[j].startswith('-'):
            j += 1
        if j < len(rest):
            rest = rest[j:]
            prog = os.path.basename(rest[0])
    if prog in _NEVER_RESTORE_COMMANDS:
        return True
    if prog == 'systemctl' and any(a in _SYSTEMCTL_POWER_ACTIONS for a in rest[1:]):
        return True
    return False


def _normalize_auto_tokens(tokens: list[str], from_proc: bool = False) -> list[str] | None:
    """Return normalized tokens if safe to auto-run, else None."""
    if not tokens:
        return None
    idx = _skip_env_assignments(tokens)
    if idx >= len(tokens):
        return None

    env_prefix = tokens[:idx]
    cmd_tokens = list(tokens[idx:])
    prog = os.path.basename(cmd_tokens[0])

    if prog not in RESTORABLE_COMMANDS:
        return None

    if from_proc and prog in _PREFER_BARE_NAME:
        cmd_tokens[0] = prog

    if prog in _RESUME_DEFAULTS:
        default_flag, resuming_flags, skip_flags = _RESUME_DEFAULTS[prog]
        args = cmd_tokens[1:]
        for a in args:
            flag = a.split('=', 1)[0]
            if flag in skip_flags:
                return None
        has_resume = any(a.split('=', 1)[0] in resuming_flags for a in args)
        if not has_resume:
            cmd_tokens.insert(1, default_flag)

    return env_prefix + cmd_tokens


def _classify_command_str(raw: str) -> tuple[str, Any] | None:
    """Classify a raw shell command string into ('auto', tokens), ('paused', raw), or None."""
    raw = raw.strip()
    if not raw:
        return None
    if any(frag in raw for frag in _UNSAFE_SHELL_FRAGMENTS):
        # Compound/piped/redirected commands are never auto-run; offer them paused
        # unless they clearly start with a power/exit command.
        first_part = raw.splitlines()[0].strip()
        try:
            head_tokens = shlex.split(first_part)
        except ValueError:
            head_tokens = first_part.split()
        if head_tokens and _is_never_restore(head_tokens):
            return None
        return ('paused', raw)
    try:
        tokens = shlex.split(raw)
    except ValueError:
        return ('paused', raw)
    if not tokens or _is_never_restore(tokens):
        return None
    if auto := _normalize_auto_tokens(tokens, from_proc=False):
        return ('auto', auto)
    return ('paused', raw)


def _classify_proc_cmdline(fcmd: list[str]) -> tuple[str, Any] | None:
    """Classify a /proc cmdline into ('auto', tokens), ('paused', shell_str), or None."""
    from kitty.shell_integration import join as shell_join

    if not fcmd or _is_never_restore(fcmd):
        return None
    if auto := _normalize_auto_tokens(fcmd, from_proc=True):
        return ('auto', auto)
    return ('paused', shell_join('fish', fcmd))


def _direct_foreground_child_cmdline(window: Any) -> list[str] | None:
    """Find the cmdline of the foreground process directly spawned by the shell."""
    root_pid = window.child.root_pid
    if root_pid is None:
        return None
    fg = window.child.foreground_processes
    if not fg:
        return None
    direct = [p for p in fg if p.get('pid') not in (None, root_pid) and _ppid_of(p['pid']) == root_pid]
    candidates = direct or [p for p in fg if p.get('pid') not in (None, root_pid)]
    if not candidates:
        return None
    # Prefer the oldest candidate (lowest pid among direct children)
    candidates.sort(key=lambda p: p['pid'])
    for proc in candidates:
        cmdline = proc.get('cmdline')
        if cmdline:
            return list(cmdline)
    return None


def _active_restore_action(window: Any) -> tuple[str, Any] | None:
    """Determine restore action for a shell window: ('auto', tokens), ('paused', str), or None."""
    if window.at_prompt:
        # Preserve an unexecuted paused command across repeated closes/reboots
        if pending := window.user_vars.get(PAUSED_USER_VAR, '').strip():
            return ('paused', pending)
        return None

    # 1. Prefer shell-integration reported command (preserves fish aliases like `top`),
    #    unless the user is currently inside `restore-paused` itself (fall through to child).
    if window.last_cmd_cmdline:
        raw = window.last_cmd_cmdline.strip()
        first = raw.split(None, 1)[0] if raw else ''
        if first != 'restore-paused':
            return _classify_command_str(raw)

    # 2. Fallback when restored via `fish -C` (or running inside `restore-paused`):
    #    inspect the direct child of the shell (never grandchild LSP/MCP servers).
    if fcmd := _direct_foreground_child_cmdline(window):
        if action := _classify_proc_cmdline(fcmd):
            return action

    # 3. Last fallback: if launched via `fish -C <cmd>` (not restore-paused.fish) and still running
    if window.creation_spec and window.creation_spec.cmd:
        cmd = window.creation_spec.cmd
        if (
            len(cmd) == 3
            and os.path.basename(cmd[0]).lstrip('-') == 'fish'
            and cmd[1] in ('-C', '--init-command')
            and RESTORE_PAUSED_SCRIPT not in cmd[2]
        ):
            return _classify_command_str(cmd[2])

    return None


def _fish_shell_exe() -> str | None:
    from kitty.fast_data_types import get_options
    from kitty.utils import resolved_shell

    shell = list(resolved_shell(get_options()))
    shell_exe = shell[0] if shell else '/bin/fish'
    if os.path.basename(shell_exe).lstrip('-') == 'fish':
        return shell_exe
    return None


def _shell_launch_for_auto(tokens: list[str]) -> list[str]:
    from kitty.shell_integration import join as shell_join

    if shell_exe := _fish_shell_exe():
        return [shell_exe, '-C', shell_join('fish', tokens)]
    return []


def _shell_launch_for_paused(raw_cmd: str) -> list[str]:
    from kitty.shell_integration import as_fish_str_literal

    if shell_exe := _fish_shell_exe():
        init_cmd = f'source -- {as_fish_str_literal(RESTORE_PAUSED_SCRIPT)} {as_fish_str_literal(raw_cmd)}'
        return [shell_exe, '-C', init_cmd]
    return []


def _rewrite_tab_block(tab_lines: list[str], boss: Any, tmux_clients: dict[int, str]) -> list[str]:
    """Fix cwds, active/paused commands, and tmux tab attach commands for one tab."""
    from kitty.constants import unserialize_launch_flag
    from kitty.launch import parse_launch_args
    from kitty.session import is_safe_for_session_line, session_launch_line
    from kitty.utils import shlex_split

    parsed_launches: dict[int, tuple[list[str], Any, str, list[str] | None, bool]] = {}
    tab_cwds: list[str] = []

    for idx, line in enumerate(tab_lines):
        if not line.startswith('launch '):
            continue
        raw_args = list(shlex_split(line[len('launch ') :], True))
        if not raw_args or not raw_args[0].startswith(unserialize_launch_flag):
            continue
        try:
            sdata = json.loads(raw_args[0][len(unserialize_launch_flag) :])
            wid = sdata.get('id')
        except (ValueError, AttributeError):
            continue
        window = boss.window_id_map.get(wid)
        if window is None:
            continue

        spec = parse_launch_args(raw_args[1:])
        opt_count = len(raw_args) - len(spec.args)
        flag_args = raw_args[:opt_count]  # includes unserialize flag at [0]
        orig_cmd = list(spec.args)

        true_cwd = _window_cwd(window)
        if true_cwd and is_safe_for_session_line(true_cwd):
            tab_cwds.append(true_cwd)

        # Determine command override
        new_cmd: list[str] | None = None
        replace_cmd = False
        creation_cmd = list(window.creation_spec.cmd) if (window.creation_spec and window.creation_spec.cmd) else []

        if _is_tmux_launch(orig_cmd) or _is_tmux_launch(creation_cmd):
            session_name = _tmux_session_for_window(window, tmux_clients) or window.user_vars.get('tmux_session')
            if session_name:
                new_cmd = [TMUX_TAB_SCRIPT, 'attach', session_name]
                replace_cmd = True
        elif _is_shell_cmd(orig_cmd) and _is_shell_cmd(creation_cmd):
            replace_cmd = True
            # Also handle tmux started manually inside a fish shell
            if tmux_session := _tmux_session_for_window(window, tmux_clients):
                new_cmd = [TMUX_TAB_SCRIPT, 'attach', tmux_session]
            elif action := _active_restore_action(window):
                kind, payload = action
                if kind == 'auto':
                    if fish_launch := _shell_launch_for_auto(payload):
                        new_cmd = fish_launch
                    else:
                        sdata['cmd_at_shell_startup'] = payload
                        flag_args[0] = unserialize_launch_flag + json.dumps(sdata)
                        new_cmd = []
                elif kind == 'paused':
                    new_cmd = _shell_launch_for_paused(payload)
            else:
                new_cmd = []

        parsed_launches[idx] = (flag_args, orig_cmd, true_cwd, new_cmd, replace_cmd)

    if not parsed_launches:
        return tab_lines

    most_common_cwd = Counter(tab_cwds).most_common(1)[0][0] if tab_cwds else ''

    out: list[str] = []
    for idx, line in enumerate(tab_lines):
        if line.startswith('cd ') and most_common_cwd:
            out.append(f'cd {most_common_cwd}')
            continue
        if idx in parsed_launches:
            flag_args, orig_cmd, true_cwd, new_cmd, replace_cmd = parsed_launches[idx]
            # Strip existing --cwd flags and transient kitty_paused_cmd user var
            # (restore-paused.fish re-sets the user var fresh on restore).
            cleaned_flags: list[str] = []
            skip_next = False
            for i, a in enumerate(flag_args):
                if skip_next:
                    skip_next = False
                    continue
                if a == '--cwd':
                    skip_next = True
                    continue
                if a.startswith('--cwd='):
                    continue
                if a == '--var' and i + 1 < len(flag_args) and flag_args[i + 1].startswith(f'{PAUSED_USER_VAR}='):
                    skip_next = True
                    continue
                if a.startswith(f'--var={PAUSED_USER_VAR}='):
                    continue
                cleaned_flags.append(a)
            if true_cwd and true_cwd != most_common_cwd:
                cleaned_flags.append(f'--cwd={true_cwd}')
            final_cmd = (new_cmd if new_cmd is not None else []) if replace_cmd else orig_cmd
            out.append(session_launch_line(['launch'] + cleaned_flags + final_cmd))
            continue
        out.append(line)
    return out


def _enhance_session(lines: list[str], boss: Any) -> str:
    tmux_clients = _tmux_client_sessions()
    result: list[str] = []
    current_tab: list[str] | None = None

    for line in lines:
        if line.startswith('new_tab') and (len(line) == 7 or line[7] == ' '):
            if current_tab is not None:
                result.extend(_rewrite_tab_block(current_tab, boss, tmux_clients))
            current_tab = [line]
        elif line.startswith('new_os_window') or line.startswith('focus_tab '):
            if current_tab is not None:
                result.extend(_rewrite_tab_block(current_tab, boss, tmux_clients))
                current_tab = None
            result.append(line)
        elif current_tab is not None:
            current_tab.append(line)
        else:
            result.append(line)

    if current_tab is not None:
        result.extend(_rewrite_tab_block(current_tab, boss, tmux_clients))
    return '\n'.join(result)


def _write_snapshot(boss: Any) -> None:
    # The same snapshot boss.save_session_at_logout() writes, minus its cleanup
    # of snapshots older than this instance: that cleanup assumes it runs at
    # logout, and while kitty runs it would delete the snapshots of every
    # kitty instance started before this one.
    from kitty import logout_session as snap
    from kitty.fast_data_types import get_options
    from kitty.main import is_panel_kitten
    from kitty.session import default_save_as_session_opts, parse_session
    from kitty.utils import lock_with_file

    if not get_options().restore_session_after_logout or is_panel_kitten():
        return
    ser_opts = default_save_as_session_opts()
    ser_opts.os_window_geometry = True
    raw_lines = list(boss.serialize_state_as_session('', ser_opts))
    if not raw_lines:
        return
    session = _enhance_session(raw_lines, boss)
    if not session:
        return
    base = snap.snapshots_dir()
    os.makedirs(os.path.dirname(base), exist_ok=True)
    key_store = snap.get_key_store()
    with lock_with_file(snap.lock_path(base)):
        ids = {w.serialized_id for s in parse_session(session, get_options()) for t in s.tabs for w in t.windows}
        scrollback = {}
        for window in boss.all_windows:
            if window.id in ids and (data := snap.scrollback_for_restore(window.screen)):
                scrollback[window.id] = data
        path = snap.save_snapshot(base, os.getpid(), session, scrollback, snap.process_state, key_store)
        try:
            snap.lock_snapshot_for_saver(path)
        except OSError:
            pass


def _save(boss: Any) -> None:
    if _state['stopped'] or boss.is_quitting:
        return
    _write_snapshot(boss)
    _state['dirty'] = False
    _state['last_save'] = time.monotonic()


def _tick(boss: Any) -> None:
    if _state['dirty'] or time.monotonic() - _state['last_save'] >= REFRESH_INTERVAL:
        _save(boss)


def _mark_dirty(boss: Any) -> None:
    _state['dirty'] = True
    if _state['timer'] is None and not _state['stopped']:
        _state['timer'] = add_timer(lambda timer_id: _tick(boss), CHECK_INTERVAL, True)


def _stop() -> None:
    _state['stopped'] = True
    if _state['timer'] is not None:
        remove_timer(_state['timer'])
        _state['timer'] = None


def on_load(boss: Any, data: dict[str, Any]) -> None:
    _mark_dirty(boss)


def on_tab_bar_dirty(boss: Any, window: Any, data: dict[str, Any]) -> None:
    _mark_dirty(boss)


def on_title_change(boss: Any, window: Any, data: dict[str, Any]) -> None:
    _mark_dirty(boss)


def on_cmd_startstop(boss: Any, window: Any, data: dict[str, Any]) -> None:
    _mark_dirty(boss)


def on_set_user_var(boss: Any, window: Any, data: dict[str, Any]) -> None:
    if data.get('key') == PAUSED_USER_VAR:
        _mark_dirty(boss)


def on_quit(boss: Any, window: Any, data: dict[str, Any]) -> None:
    # Flush any pending changes while all tabs/windows are still alive.
    if data.get('confirmed', True) and not _state['stopped'] and _state['dirty']:
        _write_snapshot(boss)
        _state['dirty'] = False
        _state['last_save'] = time.monotonic()


def on_close(boss: Any, window: Any, data: dict[str, Any]) -> None:
    # The last window is closing: kitty is about to exit. When its program
    # exits the closing window is still listed, so it does not count.
    if _state['stopped'] or any(w.id != window.id for w in boss.all_windows):
        return
    _stop()
    if boss.desktop_session_ending or boss.quit_close_event().get('cause') in ('signal', 'logout'):
        return
    if _desktop_session_ending():
        return
    from kitty import logout_session

    if logout_session.saver_lock is None:
        return
    own_path = logout_session.saver_lock[0]
    if RESTORE_AFTER_NORMAL_QUIT and not _other_live_snapshot_exists(logout_session.snapshots_dir(), own_path):
        # Last running kitty instance: keep the snapshot so reopening kitty restores it once.
        return
    logout_session.delete_snapshot(own_path)
