$ErrorActionPreference = 'Stop'
$repoDir = Split-Path -Parent $PSScriptRoot
# Custom manifests in Scoopfile.json are relative to the repository root.
Push-Location $repoDir
try {
    scoop import '.\packages\Scoopfile.json'
    if ($LASTEXITCODE -ne 0) { throw 'scoop import failed' }
} finally {
    Pop-Location
}
