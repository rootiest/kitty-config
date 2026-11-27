# Rootiest Kitty Configuration

```none
 ██▀███   ▒█████   ▒█████  ▄▄▄█████▓ ██▓▓█████   ██████ ▄▄▄█████▓
▓██ ▒ ██▒▒██▒  ██▒▒██▒  ██▒▓  ██▒ ▓▒▓██▒▓█   ▀ ▒██    ▒ ▓  ██▒ ▓▒
▓██ ░▄█ ▒▒██░  ██▒▒██░  ██▒▒ ▓██░ ▒░▒██▒▒███   ░ ▓██▄   ▒ ▓██░ ▒░
▒██▀▀█▄  ▒██   ██░▒██   ██░░ ▓██▓ ░ ░██░▒▓█  ▄   ▒   ██▒░ ▓██▓ ░
░██▓ ▒██▒░ ████▓▒░░ ████▓▒░  ▒██▒ ░ ░██░░▒████▒▒██████▒▒  ▒██▒ ░
░ ▒▓ ░▒▓░░ ▒░▒░▒░ ░ ▒░▒░▒░   ▒ ░░   ░▓  ░░ ▒░ ░▒ ▒▓▒ ▒ ░  ▒ ░░
  ░▒ ░ ▒░  ░ ▒ ▒░   ░ ▒ ▒░     ░     ▒ ░ ░ ░  ░░ ░▒  ░ ░    ░
  ░░   ░ ░ ░ ░ ▒  ░ ░ ░ ▒    ░       ▒ ░   ░   ░  ░  ░    ░
   ░         ░ ░      ░ ░            ░     ░  ░      ░
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░▒▓████████▓▒░▒▓████████▓▒░▒▓█▓▒░░▒▓█▓▒░
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░  ░▒▓█▓▒░      ░▒▓█▓▒░   ░▒▓█▓▒░░▒▓█▓▒░
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░  ░▒▓█▓▒░      ░▒▓█▓▒░   ░▒▓█▓▒░░▒▓█▓▒░
░▒▓███████▓▒░░▒▓█▓▒░  ░▒▓█▓▒░      ░▒▓█▓▒░    ░▒▓██████▓▒░
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░  ░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░  ░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░  ░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░

        ▄████▄   ▒█████   ███▄    █   █████▒
        ▒██▀ ▀█  ▒██▒  ██▒ ██ ▀█   █ ▓██   ▒
        ▒▓█    ▄ ▒██░  ██▒▓██  ▀█ ██▒▒████ ░
        ▒▓▓▄ ▄██▒▒██   ██░▓██▒  ▐▌██▒░▓█▒  ░
        ▒ ▓███▀ ░░ ████▓▒░▒██░   ▓██░░▒█░
        ░ ░▒ ▒  ░░ ▒░▒░▒░ ░ ▒░   ▒ ▒  ▒ ░
        ░  ▒     ░ ▒ ▒░ ░ ░░   ░ ▒░ ░
        ░        ░ ░ ░ ▒     ░   ░ ░  ░ ░
        ░ ░          ░ ░           ░
        ░

            _..---...,""-._     ,/}/)
         .''        ,      ``..'(/-<
        /   _      {      )         \
       ;   _ `.     `.   <         a(
     ,'   ( \  )      `.  \ __.._ .: y
    (  <\_-) )'-.____...\  `._   //-'
     `. `-' /-._)))      `-._)))
       `...'
```

The rootiest kitty configuration you will ever see!

## Installation

1. Install [kitty](https://sw.kovidgoyal.net/kitty/)

2. Install pre-requisites

   - Required
     - [Nerd Fonts](https://github.com/ryanoasis/nerd-fonts/) -
       Nerd Fonts glyphs are required.
     - [Rootiest Iosevka](https://git.rootiest.dev/rootiest/rootiest-iosevka) -
       the terminal font.
   - Optional
     - [fish](https://fishshell.com/)
     - [neovim](https://neovim.io/)
     - [tmux](https://github.com/tmux/tmux) and [fzf](https://github.com/junegunn/fzf) (for restorable tmux tabs)

3. Backup your current kitty configuration (if you have one)

   ```bash
   mv ~/.config/kitty ~/.config/kitty.bak
   ```

4. Clone the repository

   ```bash
   git clone https://git.rootiest.dev/rootiest/kitty-conf.git ~/.config/kitty
   ```

5. **Enjoy!** 🎉

## Features

- Smart key bindings with NeoVim-aware passthrough
- Integration with NeoVim (kitty-scrollback.nvim for in-editor scrollback)
- Integration with fish shell
- Automatic scrollback history logging on every window/pane close
- Automatic session autosave and restore across reboots and closing the last kitty window (`session-autosave.py`)
- Restorable tmux tabs with fzf session picker (`tmux-tab.sh`)
- Catppuccin Mocha theme with 75% background opacity and blur
- Cursor trail effect for enhanced visibility
- Highly-tuned Iosevka Rootiest v2 font with custom OpenType features
- Wayland-native display
- Single clean session with splits layout
- Manual session dump (F11) and config reload (F12)
- Integrates cleanly with other Rootiest projects

## Configuration

### Session Restore

`session-autosave.py` keeps kitty's logout snapshot (`restore_session_after_logout yes`) continuously updated (5s after tab/title/command changes, and every 5 minutes for scrollback) so tabs, titles, split layouts, working directories, and scrollback restore automatically after a logout, reboot, or accidentally closing the last kitty window. Secondary kitty instances closed while another kitty is still open discard their own snapshot so new windows open cleanly.

- **Auto-resumed commands:** strictly safe interactive sessions (e.g. `claude` → `claude --resume`, `agy` → `agy --continue`, `top`/`btop`/`htop`, `lazygit`, `yazi`, `less`) restart automatically via `fish -C` after `config.fish` finishes loading.
- **Paused commands:** other active commands (e.g. `nvim`, `ssh`, package managers, pipelines) are not auto-run; instead, `restore-paused.fish` prints the command, stores it in `$KITTY_PAUSED_COMMAND`, and defines a one-shot `restore-paused` (`--clear` to dismiss) command for that tab.
- **Tmux tabs:** tabs started with `tmux-tab.sh` or `tmux` are saved as `tmux-tab.sh attach <session>` so they wait for tmux-continuum and reattach to their original session.

### Scrollback History

Terminal scrollback is automatically saved to `~/.terminal_history/` whenever a window or pane is closed (including `Ctrl+D`, closing a pane via keybind, or quitting kitty). The fish `smart_exit` function handles graceful shell exits; `watcher.py` catches all other close events.

| Variable | Default | Description |
|---|---|---|
| `SCROLLBACK_HISTORY_DIR` | `~/.terminal_history` | Directory where scrollback logs are written |
| `SCROLLBACK_HISTORY_MAX_FILES` | `100` | Maximum number of log files to retain |

## Companion Tools

[Rootiest Fish](https://git.rootiest.dev/rootiest/fish-config) -
Fish shell configuration that pairs well with this kitty configuration
and the NeoVim configuration.

[Rootiest Tmux](https://git.rootiest.dev/rootiest/tmux-config) -
A tmux configuration that is designed to work with this kitty config.

[Rootiest Neovim](https://git.rootiest.dev/rootiest/neovim-config) -
A NeoVim config built to work alongside this and the fish config.

[Rootiest Iosevka Font](https://git.rootiest.dev/rootiest/rootiest-iosevka) -
A custom Iosevka font that is designed by developers, for developers.

[Nerd Fonts](https://github.com/ryanoasis/nerd-fonts) -
A collection of fonts that include many icons and glyphs that are used in this configuration.

## Dotfiles

[Rootiest Dotfiles](https://github.com/rootiest/dotfiles)

## Credits

- [kitty](https://sw.kovidgoyal.net/kitty/)
- [kitty-scrollback](https://github.com/mikesmithgh/kitty-scrollback.nvim)
- [vim-kitty-navigator](https://github.com/knubie/vim-kitty-navigator)
