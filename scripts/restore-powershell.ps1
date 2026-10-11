# Run with pwsh74 (PowerShell 7.4+) after restoring Scoop packages.
# Module versions are explicit; shell startup never downloads modules.
#Requires -Version 7.4
$ErrorActionPreference = 'Stop'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot '../packages/PowerShellModules.json') -Raw |
    ConvertFrom-Json
foreach ($entry in $manifest.PSObject.Properties) {
    if (Get-Module -ListAvailable -Name $entry.Name | Where-Object { $_.Version -eq [version]$entry.Value }) {
        continue
    }
    Install-PSResource -Name $entry.Name -Version $entry.Value -Scope CurrentUser `
        -Repository PSGallery -TrustRepository -AcceptLicense
}
