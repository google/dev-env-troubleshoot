<#
 Copyright 2026 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
#>

# Installs gcheck on Windows via pipx.
#
# Works two ways:
#   1. Local clone:
#        .\install.ps1
#      Installs editably from this checkout -- code edits apply immediately.
#   2. One-liner (once the repo is public):
#        powershell -c "irm https://raw.githubusercontent.com/google/dev-env-troubleshoot/main/install.ps1 | iex"
#      Installs straight from GitHub, no local clone needed.
#
# It tells the two apart by checking whether $PSScriptRoot points at a real
# checkout containing pyproject.toml -- piped/iex'd scripts have no
# $PSScriptRoot, since there's no file on disk to resolve.
#
# If PowerShell blocks a locally-saved copy with an execution-policy error:
#   powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"

# pipx (and pip) print Unicode characters -- e.g. the "done! (sparkle) (star)
# (sparkle)" success message -- unconditionally. Python's stdout defaults to
# the console's active code page, and on a non-UTF-8 code page (still common
# on Windows, e.g. legacy 1252) encoding those characters raises
# UnicodeEncodeError and crashes pipx mid-command, which otherwise looks like
# a mysterious failure unrelated to anything this script did. Force Python's
# I/O to UTF-8 regardless of the console's code page.
$env:PYTHONUTF8 = "1"

$GcheckRepoUrl = "https://github.com/google/dev-env-troubleshoot.git"
$GcheckRawBaseUrl = "https://raw.githubusercontent.com/google/dev-env-troubleshoot/main"

function Find-Python {
    foreach ($candidate in @("python", "py")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        try {
            & $candidate -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch {}
    }
    return $null
}

Write-Host "==> Checking for Python 3.10+"
$python = Find-Python

# Piped installs (irm | iex) and CI runs have no console to prompt on --
# $env:CI is set by GitHub Actions (and most other CI systems) by convention,
# and UserInteractive is false for non-interactive hosts. Fall back to just
# printing instructions in either case, matching the old behavior.
$canPrompt = [Environment]::UserInteractive -and -not $env:CI

if (-not $python) {
    Write-Host "error: Python 3.10+ not found." -ForegroundColor Red
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        if ($canPrompt) {
            try {
                $reply = Read-Host "Install it now with 'winget install Python.Python.3.12'? [Y/n]"
            } catch {
                $reply = "n"
            }
            if ($reply -match '^[nN]') {
                Write-Host "Install it with: winget install Python.Python.3.12"
                exit 1
            }
            Write-Host "==> Installing Python via winget"
            winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) {
                Write-Host "error: winget install failed." -ForegroundColor Red
                exit 1
            }
            # winget updates the registry's PATH, not this already-running
            # process's -- reload it so Find-Python can see the new install
            # without needing a new terminal window.
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
            $python = Find-Python
            if (-not $python) {
                Write-Host "error: installed Python still not detected. Open a new terminal and rerun this script." -ForegroundColor Red
                exit 1
            }
        } else {
            Write-Host "Install it with: winget install Python.Python.3.12"
            exit 1
        }
    } else {
        Write-Host "Install it from https://www.python.org/downloads/ , then rerun this script."
        exit 1
    }
}

$pythonVersion = & $python --version
Write-Host "==> Using $pythonVersion ($python)"

# Returns the path to pipx-requirements.txt (the hash-locked bootstrap deps
# for `pip install --require-hashes`), downloading it to a temp file first
# when run as a piped one-liner (irm | iex), since then there's no local
# checkout to find it next to. Sets $script:pipxReqsIsTemp so the caller
# knows whether to clean the returned path up afterwards.
$script:pipxReqsIsTemp = $false
function Resolve-PipxRequirements {
    if ($PSScriptRoot) {
        $candidate = Join-Path $PSScriptRoot "pipx-requirements.txt"
        if (Test-Path $candidate) {
            $script:pipxReqsIsTemp = $false
            return $candidate
        }
    }
    $tmp = New-TemporaryFile
    try {
        Invoke-WebRequest -Uri "$GcheckRawBaseUrl/pipx-requirements.txt" -OutFile $tmp.FullName -UseBasicParsing
    } catch {
        Write-Host "error: couldn't download pipx-requirements.txt." -ForegroundColor Red
        Remove-Item $tmp.FullName -Force -ErrorAction SilentlyContinue
        exit 1
    }
    $script:pipxReqsIsTemp = $true
    return $tmp.FullName
}

# Invokes pipx the way it's actually available in this session: as the
# `pipx` executable if it was already on PATH, or via `python -m pipx` if we
# just installed it as a module (a freshly-installed pipx.exe shim isn't
# guaranteed to be resolvable here yet, same PATH-timing issue as the
# Python/winget reload above).
$script:pipxViaModule = $false
function Invoke-Pipx {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$PipxArgs)
    if ($script:pipxViaModule) {
        & $python -m pipx @PipxArgs
    } else {
        & pipx @PipxArgs
    }
}

# Best-effort `pipx uninstall` used only to clear a stale venv before a
# fallback install retry -- failure here (nothing installed, files locked by
# a still-running gcheck, etc.) should never abort the script. Under this
# script's global $ErrorActionPreference = "Stop", redirecting a native
# command's stderr (e.g. `*> $null`) makes PowerShell 5.1 wrap it into a
# terminating NativeCommandError, so this swaps in "Continue" for the call
# instead of redirecting streams.
function Invoke-PipxUninstallQuiet {
    param([string]$PackageName)
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        Invoke-Pipx uninstall $PackageName | Out-Null
    } catch {
    } finally {
        $ErrorActionPreference = $prevEap
    }
}

Write-Host "==> Checking for pipx"
if (-not (Get-Command pipx -ErrorAction SilentlyContinue)) {
    Write-Host "==> pipx not found, installing it"
    # --require-hashes pins pipx (and its own dependencies) to the exact,
    # known-good artifacts recorded in pipx-requirements.txt, so a
    # compromised or typosquatted PyPI upload can't slip in here unnoticed.
    $pipxReqs = Resolve-PipxRequirements
    & $python -m pip install --user --require-hashes -r $pipxReqs
    if ($LASTEXITCODE -ne 0) {
        # `--user` installs are rejected inside a virtualenv ("User
        # site-packages are not visible in this virtualenv"). $python can
        # easily resolve to a project-specific venv interpreter (e.g. from
        # PlatformIO, a VS Code extension, etc.) that happens to be first on
        # PATH rather than a real system install -- installing straight into
        # it (no --user) works fine in that case.
        Write-Host "==> '--user' install failed, retrying without --user (this can happen when the selected Python is a virtualenv interpreter)"
        & $python -m pip install --require-hashes -r $pipxReqs
        if ($LASTEXITCODE -ne 0) {
            Write-Host "error: 'pip install pipx' failed." -ForegroundColor Red
            exit 1
        }
    }
    if ($script:pipxReqsIsTemp) {
        Remove-Item $pipxReqs -Force -ErrorAction SilentlyContinue
    }
    & $python -m pipx ensurepath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "error: 'pipx ensurepath' failed." -ForegroundColor Red
        exit 1
    }
    $script:pipxViaModule = $true
}

$localCheckout = $null
if ($PSScriptRoot) {
    $candidate = Join-Path $PSScriptRoot "pyproject.toml"
    if (Test-Path $candidate) { $localCheckout = $PSScriptRoot }
}

if ($localCheckout) {
    Write-Host "==> Installing gcheck (editable) from local checkout: $localCheckout"
    Invoke-Pipx install --force --editable "$localCheckout"
    if ($LASTEXITCODE -ne 0) {
        # A pre-existing pipx defaults to the uv backend when uv is on PATH,
        # and rejects an uv that's older than it requires (e.g. "pipx needs
        # uv>=0.9.17, but ... reports 0.8.2"). Rather than parse that message,
        # just retry once with the pip backend, which pipx always supports.
        # A venv from an earlier attempt (this one or an older run of this
        # script) records its backend at creation time, so --force alone
        # won't flip it -- uninstall first (ignore failure if it never
        # existed) so the retry actually creates a fresh pip-backed venv.
        Write-Host "==> pipx install failed, retrying with --backend pip (uv may be missing or outdated)"
        Invoke-PipxUninstallQuiet gcheck
        Invoke-Pipx install --force --editable "$localCheckout" --backend pip
        if ($LASTEXITCODE -ne 0) {
            Write-Host "error: 'pipx install' failed." -ForegroundColor Red
            exit 1
        }
    }
} else {
    Write-Host "==> Checking for git"
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "error: git not found -- required to install gcheck from GitHub." -ForegroundColor Red
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Host "Install it with: winget install Git.Git"
        } else {
            Write-Host "Install it from https://git-scm.com/downloads , then rerun this script."
        }
        exit 1
    }
    Write-Host "==> Installing gcheck from $GcheckRepoUrl"
    Invoke-Pipx install --force "git+$GcheckRepoUrl"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "==> pipx install failed, retrying with --backend pip (uv may be missing or outdated)"
        Invoke-PipxUninstallQuiet gcheck
        Invoke-Pipx install --force "git+$GcheckRepoUrl" --backend pip
        if ($LASTEXITCODE -ne 0) {
            Write-Host "error: 'pipx install' failed." -ForegroundColor Red
            exit 1
        }
    }
}

Write-Host ""
Write-Host "Done. Run 'gcheck' to start."
Write-Host "If 'gcheck' isn't found, open a new terminal window (pipx just updated your PATH)."
