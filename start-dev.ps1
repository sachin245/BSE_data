# start-dev.ps1
# ------------------------------------------------------------
# Full Stack Development Launcher for BSE_data
# 1. Environment Setup (Python Venv + Dependencies)
# 2. Application Launch (FastAPI + React + Streamlit)
# ------------------------------------------------------------

$PSScriptRoot = Get-Location

# 1. Setup Python Virtual Environment
if (-not (Test-Path "$PSScriptRoot\.venv")) {
    Write-Host "Creating Python virtual environment..."
    python -m venv .venv
}

# 2. Activate and Install Dependencies
$activateScript = Join-Path -Path $PSScriptRoot -ChildPath ".venv\Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    Write-Host "Activating venv and checking dependencies..."
    . $activateScript
    python -m pip install --upgrade pip
    
    # Install backend requirements
    $reqPath = Join-Path -Path $PSScriptRoot -ChildPath "backend\requirements.txt"
    if (Test-Path $reqPath) {
        pip install -r $reqPath
    }
    
    # Ensure Streamlit is installed (needed for the data control panel)
    pip install streamlit pandas
} else {
    Write-Error "Virtual environment activation script not found."
    exit 1
}

# 3. Setup React Frontend
$frontendDir = Join-Path -Path $PSScriptRoot -ChildPath "frontend"
if (Test-Path $frontendDir) {
    if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
        Write-Host "Installing frontend dependencies (npm install)..."
        Push-Location $frontendDir
        npm install
        Pop-Location
    }
}

# 4. Launch Application
Write-Host "Launching servers..."

# Launch Backend (FastAPI)
$backendCommand = "uvicorn backend.server.main:app --reload --port 8000"
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", ". '$activateScript'; $backendCommand" -WorkingDirectory $PSScriptRoot

# Launch Frontend (React)
if (Test-Path $frontendDir) {
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", "npm run dev" -WorkingDirectory $frontendDir
}

# Launch Data Control (Streamlit)
if (Test-Path "$PSScriptRoot\app.py") {
    $streamlitCommand = "streamlit run app.py"
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", ". '$activateScript'; $streamlitCommand" -WorkingDirectory $PSScriptRoot
}

Write-Host "All processes started."
Write-Host "FastAPI Backend:  http://localhost:8000"
Write-Host "React Frontend:    http://localhost:5173"
Write-Host "Streamlit Control: http://localhost:8501"
