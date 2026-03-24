# After Agent completes, optionally submit a follow-up to refresh docs-site/ (once per loop).
$ErrorActionPreference = "Stop"
try {
    $raw = @($input) -join ""
    if ([string]::IsNullOrWhiteSpace($raw)) {
        $raw = [Console]::In.ReadToEnd()
    }
    if ([string]::IsNullOrWhiteSpace($raw)) {
        Write-Output "{}"
        exit 0
    }
    $j = $raw | ConvertFrom-Json
    $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    $flag = Join-Path $projectRoot ".cursor\doc-refresh-needed.flag"

    $status = [string]$j.status
    $loop = 0
    if ($null -ne $j.loop_count) { $loop = [int]$j.loop_count }

    if ($status -ne "completed" -or $loop -ne 0 -or -not (Test-Path -LiteralPath $flag)) {
        Write-Output "{}"
        exit 0
    }

    Remove-Item -LiteralPath $flag -Force -ErrorAction SilentlyContinue

    $msg = @'
Follow @memstate-web-docs: refresh docs-site/. Every page needs "Approach" + "How it works internally" (accurate to src/memstate). Update interfaces, internal flows, and diagrams (SVG/Mermaid) when code changes. Keep js/nav.js and data-doc-page in sync.
'@.Trim()

    @{ followup_message = $msg } | ConvertTo-Json -Compress
}
catch {
    Write-Output "{}"
}
exit 0
