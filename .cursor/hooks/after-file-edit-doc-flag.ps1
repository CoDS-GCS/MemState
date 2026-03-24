# Sets a flag when the Agent edits project code so the stop hook can queue a doc refresh.
$ErrorActionPreference = "Stop"
try {
    $raw = @($input) -join ""
    if ([string]::IsNullOrWhiteSpace($raw)) {
        $raw = [Console]::In.ReadToEnd()
    }
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $j = $raw | ConvertFrom-Json
    $path = ($j.file_path -replace "/", [string][char]0x5C).ToLowerInvariant()

    if ($path -like "*\docs-site\*" -or $path -like "*\.cursor\*") { exit 0 }

    $codeLike =
        ($path -like "*\src\memstate\*") -or
        ($path -like "*\tests\*") -or
        ($path -like "*\pyproject.toml") -or
        ($path -like "*\readme.md")

    if (-not $codeLike) { exit 0 }

    $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    $flag = Join-Path $projectRoot ".cursor\doc-refresh-needed.flag"
    New-Item -ItemType File -Path $flag -Force | Out-Null
}
catch {
    # Fail-open: never block the agent on hook errors
}
exit 0
