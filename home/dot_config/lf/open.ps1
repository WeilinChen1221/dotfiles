# Custom File Opener for lf
# Configured default applications:
# - Video: mpv
# - E-book / Document: Sumatra PDF
# - Text / Code / Config: Notepad3
# - Image: JPEGView
# - Others: System Default (Windows ShellExecute)

$targetFiles = [System.Collections.Generic.List[string]]::new()

if ($args.Count -gt 0) {
    foreach ($arg in $args) {
        if ($arg -and (Test-Path -LiteralPath $arg)) {
            $targetFiles.Add((Get-Item -LiteralPath $arg).FullName)
        }
    }
} else {
    $raw = if ($env:fx) { $env:fx } else { $env:f }
    if ($raw) {
        $lines = $raw -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
        foreach ($line in $lines) {
            if (Test-Path -LiteralPath $line) {
                $targetFiles.Add((Get-Item -LiteralPath $line).FullName)
            }
        }
    }
}

if ($targetFiles.Count -eq 0) { exit 0 }

# Resolve Scoop applications or fallback to PATH
$scoopApps = Join-Path $env:USERPROFILE 'scoop\apps'
$scoopShims = Join-Path $env:USERPROFILE 'scoop\shims'

function Resolve-App {
    param([string]$AppExe, [string]$AppName)
    $direct = Join-Path $scoopApps "$AppName\current\$AppExe"
    if (Test-Path -LiteralPath $direct) { return $direct }
    $shim = Join-Path $scoopShims "$AppExe"
    if (Test-Path -LiteralPath $shim) { return $shim }
    $cmd = Get-Command $AppExe -CommandType Application -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$mpvApp     = Resolve-App 'mpv.exe' 'mpv'
$sumatraApp = Resolve-App 'SumatraPDF.exe' 'sumatrapdf'
$notepadApp = Resolve-App 'Notepad3.exe' 'notepad3'
$jpegApp    = Resolve-App 'JPEGView.exe' 'jpegview'

$videos = [System.Collections.Generic.List[string]]::new()
$ebooks = [System.Collections.Generic.List[string]]::new()
$images = [System.Collections.Generic.List[string]]::new()
$texts  = [System.Collections.Generic.List[string]]::new()
$others = [System.Collections.Generic.List[string]]::new()

$videoExts = '\.(mp4|mkv|avi|mov|wmv|flv|webm|m4v|ts|m2ts|mts|rmvb|rm|3gp|vob|mpg|mpeg|ogv|divx|f4v|mp3|flac|wav|m4a|ogg|opus|wma|aac|ape|alac)$'
$ebookExts = '\.(pdf|epub|mobi|azw|azw3|djvu|djv|chm|fb2|fb2z|zfb2|cbz|cbr|cb7|cbt)$'
$imageExts = '\.(jpg|jpeg|png|gif|bmp|webp|svg|ico|tiff|tif|avif|heic|heif|jxl|psd|raw|cr2|nef|arw|dng)$'
$textExts  = '\.(txt|md|markdown|rst|log|ini|conf|cfg|json|jsonc|yaml|yml|toml|xml|csv|tsv|ps1|psm1|psd1|bat|cmd|sh|bash|zsh|fish|py|js|ts|jsx|tsx|html|htm|css|scss|sass|less|c|cpp|h|hpp|cs|go|rs|java|kt|lua|sql|vim|vue|php|rb|swift|env|reg|nfo|diz|gitignore|gitattributes|editorconfig|diff|patch)$'

foreach ($file in $targetFiles) {
    if (Test-Path -LiteralPath $file -PathType Container) { continue }
    $ext = [IO.Path]::GetExtension($file)

    if ($ext -match "(?i)$videoExts") {
        $videos.Add($file)
    } elseif ($ext -match "(?i)$ebookExts") {
        $ebooks.Add($file)
    } elseif ($ext -match "(?i)$imageExts") {
        $images.Add($file)
    } elseif ($ext -match "(?i)$textExts" -or [string]::IsNullOrEmpty($ext)) {
        $texts.Add($file)
    } else {
        $others.Add($file)
    }
}

# 1. Video -> mpv
if ($videos.Count -gt 0) {
    if ($mpvApp) {
        Start-Process -FilePath $mpvApp -ArgumentList ($videos | ForEach-Object { "`"$_`"" })
    } else {
        foreach ($v in $videos) { Start-Process -FilePath $v }
    }
}

# 2. E-book -> Sumatra PDF
if ($ebooks.Count -gt 0) {
    if ($sumatraApp) {
        Start-Process -FilePath $sumatraApp -ArgumentList ($ebooks | ForEach-Object { "`"$_`"" })
    } else {
        foreach ($b in $ebooks) { Start-Process -FilePath $b }
    }
}

# 3. Image -> JPEGView
if ($images.Count -gt 0) {
    if ($jpegApp) {
        foreach ($img in $images) {
            Start-Process -FilePath $jpegApp -ArgumentList "`"$img`""
        }
    } else {
        foreach ($img in $images) { Start-Process -FilePath $img }
    }
}

# 4. Text -> Notepad3
if ($texts.Count -gt 0) {
    if ($notepadApp) {
        foreach ($txt in $texts) {
            Start-Process -FilePath $notepadApp -ArgumentList "`"$txt`""
        }
    } else {
        foreach ($txt in $texts) { Start-Process -FilePath $txt }
    }
}

# 5. Others -> Windows Default
foreach ($oth in $others) {
    Start-Process -FilePath $oth
}
