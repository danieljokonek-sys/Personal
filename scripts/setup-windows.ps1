<#
.SYNOPSIS
    Sets up the Max for Live devices repository on your Windows machine.

.DESCRIPTION
    Clones the repo (or pulls latest), copies device files to the local
    development folder, and creates a symlink in Ableton's User Library
    so devices appear in Live's browser.

.NOTES
    Run this in PowerShell from any directory.
    Requires: git, Ableton Live Suite with Max for Live.
#>

param(
    [string]$DevRoot = "C:\Users\Owner\Claude Bots\max4live bots",
    [string]$Branch = "claude/max4live-devices-repo-iX92U",
    [string]$RepoUrl = "https://github.com/danieljokonek-sys/personal.git"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Max for Live Devices Setup ===" -ForegroundColor Cyan
Write-Host ""

# ─── Step 1: Create dev folder ───────────────────────────────────────

if (-not (Test-Path $DevRoot)) {
    Write-Host "Creating development folder: $DevRoot" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $DevRoot -Force | Out-Null
}

# ─── Step 2: Clone or update repo ────────────────────────────────────

$RepoDir = Join-Path $DevRoot "repo"

if (Test-Path (Join-Path $RepoDir ".git")) {
    Write-Host "Repository exists. Pulling latest changes..." -ForegroundColor Yellow
    Push-Location $RepoDir
    git fetch origin $Branch
    git checkout $Branch
    git pull origin $Branch
    Pop-Location
} else {
    Write-Host "Cloning repository..." -ForegroundColor Yellow
    git clone -b $Branch $RepoUrl $RepoDir
}

Write-Host "Repository ready at: $RepoDir" -ForegroundColor Green

# ─── Step 3: Verify device files exist ───────────────────────────────

$MixFeedbackDir = Join-Path $RepoDir "devices\effects\mix-feedback"
$RequiredFiles = @(
    "mix-feedback.amxd",
    "mix-feedback-engine.js",
    "mf-analysis-core.js",
    "mf-reference-profile.js",
    "mf-track-scanner.js",
    "mf-comparator.js",
    "mf-suggestions.js",
    "mf-display.js"
)

Write-Host ""
Write-Host "Checking device files..." -ForegroundColor Yellow
$allPresent = $true
foreach ($file in $RequiredFiles) {
    $path = Join-Path $MixFeedbackDir $file
    if (Test-Path $path) {
        Write-Host "  [OK] $file" -ForegroundColor Green
    } else {
        Write-Host "  [MISSING] $file" -ForegroundColor Red
        $allPresent = $false
    }
}

if (-not $allPresent) {
    Write-Host ""
    Write-Host "ERROR: Some device files are missing. Check the repo." -ForegroundColor Red
    exit 1
}

# ─── Step 4: Symlink into Ableton User Library (optional) ────────────

$AbletonUserLib = Join-Path $env:USERPROFILE "Documents\Ableton\User Library\Presets\Max Audio Effect"

if (Test-Path $AbletonUserLib) {
    $LinkPath = Join-Path $AbletonUserLib "Mix Feedback"

    if (-not (Test-Path $LinkPath)) {
        Write-Host ""
        Write-Host "Creating symlink in Ableton User Library..." -ForegroundColor Yellow
        Write-Host "  From: $LinkPath"
        Write-Host "  To:   $MixFeedbackDir"
        Write-Host ""
        Write-Host "This requires admin privileges. A UAC prompt may appear." -ForegroundColor Yellow

        try {
            New-Item -ItemType SymbolicLink -Path $LinkPath -Target $MixFeedbackDir -ErrorAction Stop | Out-Null
            Write-Host "  Symlink created. Device will appear in Live's browser." -ForegroundColor Green
        } catch {
            Write-Host "  Could not create symlink (needs admin). You can:" -ForegroundColor Yellow
            Write-Host "    1. Run this script as Administrator, or" -ForegroundColor Yellow
            Write-Host "    2. Manually copy the mix-feedback folder to:" -ForegroundColor Yellow
            Write-Host "       $AbletonUserLib" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Ableton User Library symlink already exists." -ForegroundColor Green
    }
} else {
    Write-Host ""
    Write-Host "Ableton User Library not found at default path." -ForegroundColor Yellow
    Write-Host "You'll need to manually add the device folder to Live." -ForegroundColor Yellow
    Write-Host "Device folder: $MixFeedbackDir" -ForegroundColor Yellow
}

# ─── Step 5: Print next steps ────────────────────────────────────────

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Open Ableton Live" -ForegroundColor White
Write-Host "  2. Open any Max for Live device to launch the Max editor" -ForegroundColor White
Write-Host "  3. In Max: Options > File Preferences > Add this folder:" -ForegroundColor White
Write-Host "     $MixFeedbackDir" -ForegroundColor Cyan
Write-Host "  4. Drop mix-feedback.amxd on your Master track" -ForegroundColor White
Write-Host "  5. Load 3-5 reference tracks and click Analyze Mix" -ForegroundColor White
Write-Host ""
Write-Host "Device folder: $MixFeedbackDir" -ForegroundColor Gray
Write-Host ""
