# Dotfiles

Managed with chezmoi. `.chezmoiroot` selects `home/` as the source directory.
Package manifests and maintenance scripts live outside that directory.

## macOS setup

Install [Homebrew](https://brew.sh), then run:

```sh
brew install chezmoi
chezmoi init <this-repository-url>
cd "$(chezmoi source-path)/.."
brew bundle install --file=packages/Brewfile --no-upgrade
chezmoi diff
chezmoi apply
exec zsh -l
```

Initialization asks for your Git email address. `chezmoi apply` deploys files;
package installation is an explicit step. It does not upgrade packages or restart
services automatically.

The shell configuration lives in `~/.config/zsh`. `~/.zshenv` sets `ZDOTDIR`
and loads the environment file there. Homebrew initialization belongs in
`~/.config/zsh/.zprofile`. No system-file edits are needed. This also works with
the existing `/etc/zshenv` on this Mac, which already sets `ZDOTDIR`.
The empty `~/.zshrc` and inactive `~/.zprofile` are not managed.

The existing zsh plugin loader clones its four plugins on the first interactive
shell startup, so that first startup needs network access. Plugin checkouts,
shell history, completion caches, and session files are not tracked.

## Managed configuration

| Application | Destination |
| --- | --- |
| zsh | `~/.zshenv`, `~/.config/zsh/` |
| Starship | `~/.config/starship.toml` on both platforms |
| Homebrew | `~/.Brewfile`, rendered from `packages/Brewfile` |
| Git | `~/.gitconfig`, `~/.gitignore_global` |
| tmux | `~/.tmux.conf` |
| Neovim | `~/.config/nvim/` |
| GitHub CLI | `~/.config/gh/config.yml` |
| Cabal | `~/.config/cabal/config` with the home directory templated |
| Rift | `~/.config/rift/config.toml` |
| lf | `~/.config/lf/icons` |
| mpv | `~/.config/mpv/script-opts/` |
| GnuPG | `~/.gnupg/common.conf` only |
| Terminal | `~/.config/terminal/Custom.terminal` profile export |
| arbtt | `~/Library/LaunchAgents/de.nomeata.arbtt.plist` |

Import the saved Terminal profile on a new Mac with:

```sh
open ~/.config/terminal/Custom.terminal
```

Then select Custom as the default profile in Terminal settings. The exported
profile preserves fonts, colors, window size, and Option-as-Meta without saving
window history or replacing the live preferences database.

The arbtt agent is deployed only when
`~/Documents/Code/arbtt/bin/arbtt-capture` exists. Build or restore that local
project first, rerun `chezmoi apply`, then load the agent on a new Mac with:

```sh
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/de.nomeata.arbtt.plist
```

See [the Mac inventory](docs/macos-inventory.md) for package and restore gaps.

## Daily use

```sh
chezmoi edit ~/.config/zsh/aliases.zsh
chezmoi diff
chezmoi apply

# Capture changes made directly to an existing config.
chezmoi add --secrets=error ~/.config/zsh/aliases.zsh

# Refresh the installed Homebrew package list and deploy the global Brewfile.
cd "$(chezmoi source-path)/.."
bash scripts/refresh-brewfile.sh
chezmoi apply ~/.Brewfile
brew bundle check --global --no-upgrade

# Review source changes before committing.
chezmoi git -- status --short
chezmoi git -- diff
```

Edit `packages/Brewfile` for deliberate package changes. `~/.Brewfile` is generated
from it and should not be re-added with `chezmoi add`. The `dotfiles` shell alias
runs `chezmoi git --`, so `dotfiles status` inspects this repository.

The refresh script records installed Homebrew packages and casks. It excludes
language-package managers, editor extensions, App Store apps, and service startup
settings. It also preserves installed Rift, which this Mac's Homebrew receipt
otherwise omits from `brew bundle dump`.

## Windows

With Scoop and chezmoi installed, initialize this repo and restore packages before
applying settings:

```powershell
chezmoi init https://github.com/WeilinChen1221/dotfiles.git
Set-Location (Split-Path (chezmoi source-path) -Parent)
& .\scripts\restore-scoop.ps1
pwsh74 -NoProfile -File .\scripts\restore-powershell.ps1
chezmoi diff
chezmoi apply
```

`restore-scoop.ps1` runs Scoop import from the repository root so the saved custom
FFmpeg manifest resolves correctly. Scoop installs missing packages and restores
the held-package flag. The manifest records versions; ordinary bucket packages
are not a version lockfile.

Refresh the package inventory after changing your Scoop installation:

```powershell
Set-Location (Split-Path (chezmoi source-path) -Parent)
& .\scripts\refresh-scoopfile.ps1
chezmoi git -- diff -- packages
```

The export uses UTF-8, omits volatile update timestamps, and saves manifests for
packages installed from generated manifests. It excludes Scoop's local config,
which can contain proxy credentials.

Alongside PowerShell, AutoHotkey, mpv, and aria2, chezmoi manages Windows Terminal,
JPEGView, HWiNFO, CrystalDiskInfo, Locale Emulator, Notepad3 preferences and themes,
Mp3tag actions and field layouts, and beets settings. See
[the Windows inventory](docs/windows-inventory.md) for paths and exclusions.

Notepad3's template preserves existing local recent-file/search history at apply
time. Use `chezmoi edit` for its preferences; do not re-add its live INI, which
would copy history into the repository. Its Favorites path uses Scoop's persistent
directory rather than a versioned installation directory.

macOS ignores the Windows paths. Mac-specific configs are excluded on Windows.

## Shared shell settings

`home/.chezmoidata.toml` is the source for common command shortcuts, fzf discovery,
fzf appearance and preview commands, and the 100,000-entry history limit. Chezmoi
renders separate zsh and PowerShell implementations. Edit this data file to change
a common value, then apply on each machine. Do not re-add the rendered alias or
fzf files, which would replace their templates with machine-specific output.

Starship uses one `home/dot_config/starship.toml.tmpl` template. Both shells set
`STARSHIP_CONFIG` to `~/.config/starship.toml`; the previous zsh-local copy is
removed on macOS. Windows omits the Rust prompt module and receives a Windows
symbol. The existing macOS Neovim and Rust setup remains unchanged.

Windows loads `~/.config/powershell/profile.ps1` from the PowerShell 7 all-hosts
profile in `Documents/PowerShell/profile.ps1`. Windows PowerShell 5.1 keeps a
compatibility loader in its existing profile location. Proxy, Notepad3 editor,
UTF-8 encoding and literal-path `cdl` navigation are retained. Interactive modules
load only in a console with unredirected input and output. Startup performs no
package downloads or module updates.

`packages/PowerShellModules.json` records PSReadLine, PSFzf and posh-git versions.
Restore them with `scripts/restore-powershell.ps1`, which requires PowerShell 7.4
or later. The legacy 5.1 shell uses the features of its available modules.

| Key or command | PowerShell behavior |
| --- | --- |
| Escape | Vi command mode; insert mode uses a beam cursor, command mode a block |
| Ctrl+R | Fuzzy command history, inserted without executing |
| Ctrl+T | Fuzzy files, including hidden files, with bat preview |
| Ctrl+F | Fuzzy files excluding hidden files; inserted with PowerShell quoting |
| Alt+C | Fuzzy directory navigation |
| Ctrl+Left / Ctrl+Right | Move by word |
| Ctrl+backslash | Toggle history predictions |
| Up / Down | Substring history search, newest first, with duplicates suppressed |
| Tab | PowerShell completion menu; posh-git supplies Git completions |
| Bare directory path, then Enter | Change to that literal directory |
| `-` | Return to the previous directory in PowerShell 7 |
| `lf` | Exit lf into its last directory; temporary files are cleaned up |
| `glog`, `gadog` | Git logs using less; pager variables are restored afterward |
| `diff file1 file2` | Git's colored file diff; exit code 1 means files differ |
| `df` | Windows drive capacity in GiB |
| `stream -ListDevices` | List camera names; use `stream -Camera <name>` to view one |

`ls`, `ll`, `la`, `tree`, `cat`, `grep`, `cx` and `dotfiles` share their fixed
arguments with zsh. PowerShell implements them as functions and removes conflicting
built-in aliases. Use `Get-ChildItem`, `Get-Content` and `Compare-Object` when you
need PowerShell objects instead of native CLI output. `cx` requires a separately
installed Codex CLI. No Windows Neovim alias or Rust environment is added.

fnm replaces the POSIX-only `nvm.sh` loader on Windows. Install your desired Node
version with `fnm install <version>` and choose a default with `fnm default <version>`.
The prompt checks `.nvmrc`, `.node-version` and `package.json` after navigation,
including `z`, `lf` and `cdl`. Version files and installed Node versions are local
to your projects and machine. PowerShell's globbing differs from zsh; the zsh
numeric-glob-sort option has no direct PowerShell equivalent. GPG TTY, man-page
pager and Homebrew initialization remain macOS-specific.

This Windows machine runs build 19044. PowerShell 7.6.6 fails during runtime
startup with a CET compatibility error on it. The custom, SHA-256-verified
`packages/manifests/pwsh74.json` installs PowerShell 7.4.20 as `pwsh74`, alongside
other PowerShell installations. Windows Terminal defaults to this working
version and retains the Windows PowerShell 5.1 profile. The package is held;
PowerShell 7.4 support ends on 2026-11-10. Update Windows before switching to the
newer runtime, then update the package manifest and Terminal command together.

To sync a committed change on the other machine:

```sh
chezmoi git -- pull --ff-only
chezmoi diff
chezmoi apply
```

History files, caches, zoxide databases and installed PowerShell modules are
local state. PowerShell history is under `~/.local/state/powershell/`; the first
interactive startup copies existing PSReadLine history there if needed. Duplicate
suppression affects recall, not the contents of the saved file. Leading-space
commands are excluded while preserving PSReadLine's existing history filter.

Run the shell checks on Windows with:

```powershell
pwsh74 -NoProfile -File .\scripts\test-shell.ps1
```

The checks exercise rendered modules, Vi keymaps, literal paths, Unicode,
pipeline input, fd/fzf discovery, history matching, lf cleanup and prompt hooks.
Also exercise the interactive pickers in a fresh Terminal tab after changing
their bindings or preview settings.

## Excluded data

Credentials, SSH private keys, GnuPG keyrings, password stores, GitHub login
state, Homebrew trust records, shell sessions, caches, Python environments, and
downloaded zsh plugins stay outside the managed configuration. Authenticate tools
separately on a new machine.

References: [chezmoi ignore rules](https://www.chezmoi.io/reference/special-files/chezmoiignore/)
and [Homebrew Bundle](https://docs.brew.sh/Brew-Bundle-and-Brewfile).
