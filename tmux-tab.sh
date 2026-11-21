#!/usr/bin/env bash
# Copyright (c) 2026 Rootiest
# SPDX-License-Identifier: AGPL-3.0-or-later

# Restorable tmux tabs for kitty.
#
#   tmux-tab.sh new          start a tmux session named after $PWD (runs in the new tab)
#   tmux-tab.sh pick         fzf picker: attach, create or kill sessions (runs in an overlay)
#   tmux-tab.sh kill WIN_ID  kill the session attached in kitty window WIN_ID (runs in an overlay)
#   tmux-tab.sh list         session list used by the picker
#
# Sessions are saved by tmux-resurrect/continuum and restored when the tmux
# server starts, so they survive closing kitty and rebooting.

set -u

resurrect_last="${XDG_DATA_HOME:-$HOME/.local/share}/tmux/resurrect/last"

session_name_for() {
	# tmux session names cannot contain '.' or ':'
	local base name n=2
	base=$(basename -- "$1")
	[ "$1" = "$HOME" ] && base=home
	base=${base//[.:]/_}
	name=$base
	while tmux has-session -t "=$name" 2>/dev/null; do
		name="$base-$n"
		n=$((n + 1))
	done
	printf '%s' "$name"
}

ensure_server() {
	# Start the server if needed and give continuum's auto-restore time to
	# recreate the saved sessions before listing them
	tmux list-sessions >/dev/null 2>&1 && return
	tmux start-server
	[ -e "$resurrect_last" ] || return
	local i
	for i in $(seq 50); do
		tmux list-sessions >/dev/null 2>&1 && break
		sleep 0.1
	done
	# Wait for the restore to finish creating windows
	sleep 0.5
}

list_sessions() {
	tmux list-sessions -F "#{session_name}	#{session_windows}w	#{?session_attached,attached,}	#{s|^$HOME|~|:pane_current_path}" 2>/dev/null |
		column -t -s $'\t' -o $'\t'
}

kitty_window_for_session() {
	# Prints the id of a kitty window whose foreground process is a tmux client attached to $1
	local pids
	pids=$(tmux list-clients -t "=$1" -F '#{client_pid}' 2>/dev/null | paste -sd, -)
	[ -n "$pids" ] || return 1
	kitten @ ls | jq -r --arg pids "$pids" '
		($pids | split(",") | map(tonumber)) as $p
		| [.[].tabs[].windows[] | select(any(.pid, .foreground_processes[].pid; . as $x | $p | index($x))) | .id]
		| first // empty'
}

session_for_kitty_window() {
	# Prints the tmux session attached in kitty window $1
	local fg
	fg=$(kitten @ ls --match "id:$1" | jq -r '[.[].tabs[].windows[] | .pid, .foreground_processes[].pid] | map(tostring) | join(" ")')
	tmux list-clients -F '#{client_pid} #{session_name}' 2>/dev/null | while read -r pid name; do
		for p in $fg; do
			[ "$p" = "$pid" ] && { printf '%s' "$name"; return; }
		done
	done
}

open_session_tab() {
	local name=$1 win
	if win=$(kitty_window_for_session "$name") && [ -n "$win" ]; then
		kitten @ focus-window --match "id:$win"
	else
		kitten @ launch --type=tab --cwd="$PWD" --var "tmux_session=$name" tmux attach-session -t "=$name" >/dev/null
	fi
}

cmd_new() {
	ensure_server
	exec tmux new-session -s "$(session_name_for "$PWD")" -c "$PWD"
}

cmd_pick() {
	ensure_server
	local out query sel name
	out=$(list_sessions | fzf \
		--prompt='tmux> ' \
		--header='enter: attach · ctrl-x: kill · no match + enter: new session with that name' \
		--delimiter=$'\t' \
		--print-query \
		--with-shell='bash -c' \
		--reverse \
		--preview='tmux capture-pane -ep -t ={1}:' \
		--preview-window='right,60%' \
		--bind="ctrl-x:execute-silent(tmux kill-session -t ={1})+reload($0 list)")
	query=$(sed -n 1p <<<"$out")
	sel=$(sed -n 2p <<<"$out")
	if [ -n "$sel" ]; then
		name=$(cut -f1 <<<"$sel" | sed 's/[[:space:]]*$//')
	elif [ -n "$query" ]; then
		name=${query//[.:]/_}
		tmux has-session -t "=$name" 2>/dev/null || tmux new-session -d -s "$name" -c "$PWD"
	else
		return
	fi
	open_session_tab "$name"
}

cmd_kill() {
	local name
	name=$(session_for_kitty_window "$1")
	if [ -z "$name" ]; then
		echo "This window is not attached to a tmux session."
		read -rsn1 -p "Press any key to close."
		return
	fi
	read -rn1 -p "Kill tmux session '$name' and everything running in it? [y/N] " ans
	echo
	[[ $ans == [yY] ]] && tmux kill-session -t "=$name"
}

case "${1:-}" in
new) cmd_new ;;
pick) cmd_pick ;;
kill) cmd_kill "${2:?window id required}" ;;
list) list_sessions ;;
*)
	echo "usage: $0 new|pick|kill WIN_ID|list" >&2
	exit 2
	;;
esac
