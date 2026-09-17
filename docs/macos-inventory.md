# Mac inventory

Inspected on 2026-09-17 using `brew config`, `brew list`, `brew leaves`,
`brew tap`, `brew services list`, and `brew bundle dump`.

- Apple Silicon, Homebrew at `/opt/homebrew`, macOS 26.6.2.
- The refreshed Brewfile contains 31 formulae, 3 casks, and 3 taps.
- Added aria2, Cabal, GHC, Mole, PCRE, rust-analyzer, rustup, and Rift to the
  previous manifest. Removed battery and timewarrior, which are no longer installed.
- PostgreSQL 16 is the only service reported as started. Its database and service
  registration are local state. The manifest keeps its link setting but does not
  start or restart it. Restore databases separately; use
  `brew services start postgresql@16` if a user service is wanted on a new Mac.
- Homebrew reports a `libtiff` / `webp` dependency cycle in installed receipt
  metadata during export. The export and package check succeed. No packages were
  removed or reinstalled to address this warning.

## Restore gaps

- lf is referenced by the shell and has an icon config, but its executable is not
  currently installed. It was not added to the installed-package manifest.
- mpv has three local script-option files, which are now tracked. There is no
  macOS `mpv.conf`, `input.conf`, or scripts directory in `~/.config/mpv` to import.
  The existing Scoop mpv files belong to the Windows configuration.
- fastfetch has no custom configuration file on this Mac.
- Rift is installed from `acsandmann/tap`. Accessibility permissions and whether
  to run it as a service must be set on each Mac.
- arbtt runs from a local project under `~/Documents/Code/arbtt`, outside Homebrew.
  Its launch-agent definition is tracked, but the binary, capture logs, and local
  source project are not part of this dotfiles repository.
- Terminal's active Custom profile is exported. The live preferences database,
  window positions, recent paths, and session state are not tracked. Re-export the
  profile from Terminal settings after changing it and add the export with chezmoi.
- App logins, databases, GUI permissions, and settings stored only in application
  databases need separate backup or setup. No full `~/Library` import was made.
- The local aria2 config contains Windows paths. It remains on disk but is ignored
  by chezmoi on macOS, as is the existing `~/scoop` tree.
