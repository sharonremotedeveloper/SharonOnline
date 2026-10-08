<#
Loads the Zoom variables from the git-ignored Project-files/.env into Railway's encrypted variables for the
development environment (docs/CREDENTIALS_BROKER.md: Railway variables are the credentials broker; no custom service).
Run it yourself, logged in as sharonremotedeveloper@gmail.com (`railway whoami`). Values are never printed.
  .\scripts\railway_set_zoom_env.ps1          # dry run: lists names and which are present in .env
  .\scripts\railway_set_zoom_env.ps1 -Apply   # sets them on api, worker and beat WITHOUT triggering a deploy
#>
param([switch]$Apply, [string]$Environment = 'development',
      [string[]]$Services = @('backend-api-development', 'celery-worker-development', 'celery-beat-development'))
$names = 'ZOOM_ACCOUNT_ID','ZOOM_CLIENT_ID','ZOOM_CLIENT_SECRET','ZOOM_WEBHOOK_SECRET_TOKEN',
         'ZOOM_VIDEO_SDK_KEY','ZOOM_VIDEO_SDK_SECRET','ZOOM_VIDEO_SDK_API_KEY','ZOOM_VIDEO_SDK_API_SECRET'
$envFile = Join-Path $PSScriptRoot '..\.env'
$vals = @{}
Get-Content $envFile | ForEach-Object { if ($_ -match '^\s*([A-Z0-9_]+)=(.*)$') { $vals[$Matches[1]] = $Matches[2].Trim() } }
$who = (railway whoami) -join ' '
if ($who -notmatch 'sharonremotedeveloper@gmail.com') { throw "Wrong Railway account: $who" }
foreach ($n in $names) { "{0,-28} {1}" -f $n, $(if ($vals[$n]) { 'present' } else { 'MISSING' }) }
if (-not $Apply) { 'Dry run. Re-run with -Apply to set them.'; return }
foreach ($svc in $Services) {
  foreach ($n in $names) {
    if (-not $vals[$n]) { throw "$n missing in .env" }
    railway variables --service $svc --environment $Environment --skip-deploys --set "$n=$($vals[$n])" | Out-Null
  }
  "$svc : $($names.Count) variables set (no deploy triggered)"
}
