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
| zsh and Starship | `~/.zshenv`, `~/.config/zsh/` |
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

## Excluded data

Credentials, SSH private keys, GnuPG keyrings, password stores, GitHub login
state, Homebrew trust records, shell sessions, caches, Python environments, and
downloaded zsh plugins stay outside the managed configuration. Authenticate tools
separately on a new machine.

References: [chezmoi ignore rules](https://www.chezmoi.io/reference/special-files/chezmoiignore/)
and [Homebrew Bundle](https://docs.brew.sh/Brew-Bundle-and-Brewfile).
