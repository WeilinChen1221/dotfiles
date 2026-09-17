# Windows inventory

Inspected over SSH on 2026-09-17 on `MECHREVO-D16K` as `Admin`.
The repository is `C:\Users\Admin\.local\share\chezmoi`.

`scoop list` reports 29 apps across 5 buckets: main, extras, confetti, minecraft,
and siku. The installed app names match the previous inventory. FFmpeg now uses
a custom 7.1.1 manifest and is held. Its manifest, download URL, SHA-256, and hold
flag are saved so a restore does not silently select a different FFmpeg build.

`packages/Scoopfile.json` is now UTF-8 instead of UTF-16. The refresh script omits
timestamps and bucket manifest counts, which change without changing the setup.
No applications were installed, upgraded, removed, or restarted during this audit.

## Managed settings

| Application | Destination under the Windows home directory |
| --- | --- |
| PowerShell | `Documents/WindowsPowerShell/Microsoft.PowerShell_profile.ps1` |
| Git | `.gitconfig`, `.gitignore_global` |
| aria2 | `.aria2/aria2.conf` |
| AutoHotkey | `scoop/persist/autohotkey/scripts/mouse_binds.ahk` |
| mpv | Existing `scoop/persist/mpv/portable_config` configuration and scripts |
| Windows Terminal | `scoop/persist/windows-terminal/settings/settings.json` |
| HWiNFO | `scoop/persist/hwinfo/HWiNFO64.INI` |
| CrystalDiskInfo | `scoop/persist/crystaldiskinfo/DiskInfo.ini` |
| Locale Emulator | `scoop/persist/locale-emulator/LEConfig.xml` |
| JPEGView | `scoop/persist/jpegview/JPEGView.ini`, `KeyMap.txt` |
| Notepad3 | `scoop/persist/notepad3/Notepad3.ini`, `minipath.ini`, `Themes/` |
| Mp3tag | `scoop/persist/Mp3tag/data/actions/`, `columns.ini`, `usrfields.ini` |
| beets | `AppData/Roaming/beets/config.yaml` |

aria2 and beets use a templated home directory. The aria2 tracker list was refreshed
from the running Windows setup. Notepad3 keeps its local recent-file, find, and
replace history when preferences are applied; that history is absent from source.

The existing `.config/nvim` files remain managed, though Neovim is not installed
through Scoop. fastfetch has no custom config file. There is no Windows GitHub CLI
preferences file to import, so Windows does not receive the Mac's preferences.

## Local data and separate setup

- Rclone config, OpenList's database/config, MusicBee settings and Spotify tokens,
  and Mp3tag's opaque `mp3tag.cfg` stay local. Back them up separately with encryption.
- Music libraries, caches, logs, disk SMART history, mpv playback history, Python
  environments, and Windows Terminal `state.json` are excluded from applies.
- Everything's live configuration and search database were not imported. Managing
  selected preferences would need a separate export that excludes local search and
  service state.
- The PowerShell profile uses a local proxy at `127.0.0.1:10808`; that proxy is
  provisioned separately.
- Terminal references `JetBrainsMono Nerd Font Mono`. Fonts, file associations,
  shell integrations, startup registration, and Windows permissions are separate
  from the package/config restore.
- beets is installed outside Scoop. Its configuration is tracked; the music
  library database and import log are not.

Reference: Scoop's [export](https://github.com/ScoopInstaller/Scoop/blob/master/libexec/scoop-export.ps1)
and [import](https://github.com/ScoopInstaller/Scoop/blob/master/libexec/scoop-import.ps1)
commands.
