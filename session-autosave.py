# Copyright (c) 2026 Rootiest
# SPDX-License-Identifier: AGPL-3.0-or-later

# Keeps kitty's logout snapshot up to date so the session is restored after a
# logout or reboot.
#
# kitty saves a snapshot (tabs, splits, working directories, scrollback, window
# geometry) when the desktop portal reports that the session is ending, but
# Plasma never sends that report, and by the time kitty is closed by the
# compositor or killed by systemd its windows are already gone. So this watcher
# saves the same snapshot ahead of time: shortly after tabs, titles or running
# commands change, and every few minutes to refresh the scrollback.
#
# Quitting kitty normally deletes the snapshot, so only a logout, reboot or
# kill leaves one behind. The next kitty started without a command or
# --session restores it once. Requires restore_session_after_logout yes.

import os
import time
from typing import Any

from kitty.fast_data_types import add_timer, remove_timer

# Seconds between checks; a save happens at a check when something changed
CHECK_INTERVAL = 30.0
# Seconds after which the snapshot is refreshed even if nothing changed
REFRESH_INTERVAL = 300.0
# Keep the snapshot when kitty is quit normally, so closing and reopening
# kitty also restores the session
RESTORE_AFTER_NORMAL_QUIT = False
# Processes that run while the desktop session is ending
LOGOUT_PROCESSES = frozenset({'plasma-shutdown', 'ksmserver-logout-greeter'})

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


def _save(boss: Any) -> None:
    if _state['stopped'] or boss.is_quitting:
        return
    boss.save_session_at_logout()
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


def on_close(boss: Any, window: Any, data: dict[str, Any]) -> None:
    # The last window is gone: kitty is about to exit
    if _state['stopped'] or any(True for _ in boss.all_windows):
        return
    _stop()
    if RESTORE_AFTER_NORMAL_QUIT or boss.quit_close_event().get('cause') in ('signal', 'logout'):
        return
    if _desktop_session_ending():
        return
    from kitty import logout_session

    if logout_session.saver_lock is not None:
        logout_session.delete_snapshot(logout_session.saver_lock[0])
