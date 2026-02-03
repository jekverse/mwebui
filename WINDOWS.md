# Windows Installation Guide

## ✅ Compatibility Status

**mwebui** dapat dijalankan di Windows dengan beberapa penyesuaian.

### **Fully Compatible:**
- ✅ Python 3.8+ (Windows native)
- ✅ Flask & dependencies
- ✅ Modal SDK
- ✅ File operations (`os.path` cross-platform)
- ✅ Virtual environment

### **Requires Alternative:**
- ⚠️ Bash scripts → PowerShell/CMD equivalent
- ⚠️ `cloudflared` → Windows installer
- ⚠️ Shell paths → Windows paths

---

## 🚀 Quick Start (Windows)

### Prerequisites

1. **Python 3.8 or higher**
   - Download: https://www.python.org/downloads/
   - ✅ Check "Add Python to PATH" during installation

2. **Git for Windows**
   - Download: https://git-scm.com/download/win
   - Provides Git Bash for bash scripts

3. **Modal Account**
   - Sign up: https://modal.com

---

### Step 1: Clone Repository

```cmd
git clone https://github.com/jekverse/mwebui.git
cd mwebui\host
```

---

### Step 2: Create Virtual Environment

**Option A: CMD**
```cmd
python -m venv venv
venv\Scripts\activate
```

**Option B: PowerShell**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Note:** If PowerShell script execution is disabled:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

### Step 3: Install Dependencies

```cmd
pip install -r requirements.txt
```

---

### Step 4: Setup Modal

```cmd
modal setup
```

This will:
1. Open browser
2. Authenticate your Modal account
3. Save credentials to `%USERPROFILE%\.modal.toml`

---

### Step 5: Configure Environment Variables

#### 5.1. Create `.env` file

```cmd
copy .env.example .env
notepad .env
```

#### 5.2. Fill in your tokens

See main README.md for how to get tokens.

---

### Step 6: Deploy Secrets to Modal

#### **Option A: Using Git Bash** (Recommended)
```bash
bash create_modal_secret.sh
```

#### **Option B: Using PowerShell**

Create `create_modal_secret.ps1`:

```powershell
# Load .env file
Get-Content .env | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2])
    }
}

# Delete old secret (ignore errors)
modal secret delete my-secrets -y 2>$null

# Create new secret
modal secret create my-secrets `
    GH_TOKEN="$env:GH_TOKEN" `
    HF_TOKEN="$env:HF_TOKEN" `
    CLOUDFLARED_TOKEN="$env:CLOUDFLARED_TOKEN" `
    SSH_KEY="$env:SSH_KEY"
```

Run:
```powershell
.\create_modal_secret.ps1
```

#### **Option C: Manual (CMD)**

```cmd
modal secret delete my-secrets
modal secret create my-secrets ^
    GH_TOKEN="your_github_token" ^
    HF_TOKEN="your_huggingface_token" ^
    CLOUDFLARED_TOKEN="your_cloudflare_token" ^
    SSH_KEY="your_ssh_key"
```

---

### Step 7: (Optional) Install Cloudflared

Download Windows installer:
https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/

**Install:**
```cmd
# Download from link above, then:
cloudflared.exe install

# Verify:
cloudflared --version
```

Add to PATH if needed.

---

### Step 8: Run Application

```cmd
python app.py
```

**Access:**
- http://localhost:5000
- http://YOUR_LOCAL_IP:5000

---

## ⚠️ Windows-Specific Issues & Solutions

### Issue 1: `bash` command not found

**Solution:** Use Git Bash or PowerShell alternatives (see Step 6).

---

### Issue 2: `eventlet` greenlet errors

**Solution:** Install Windows Build Tools if needed:
```cmd
pip install eventlet --no-binary :all:
```

Or use alternative server:
```python
# In app.py, replace:
socketio.run(app, ...)

# With:
from werkzeug.serving import run_simple
run_simple('0.0.0.0', 5000, app)
```

---

### Issue 3: Path issues in code

All path operations use `os.path.join()` which is cross-platform. No changes needed.

---

### Issue 4: Modal binary location

Modal installs to:
- **Linux:** `~/.local/bin/modal`
- **Windows:** `%APPDATA%\Python\Scripts\modal.exe`

Python packages handle this automatically.

---

### Issue 5: Cloudflare Tunnel startup

The bash-based tunnel starter in `app.py` may fail. Disable it:

```python
# In app.py, comment out:
# start_cloudflare_tunnel()
```

Or run `cloudflared` manually:
```cmd
cloudflared tunnel --url http://localhost:5000
```

---

## 📝 Windows-Specific Tips

### Run in Background (Windows)

**Using `start` command:**
```cmd
start /B python app.py
```

**Using `pythonw` (no console):**
```cmd
pythonw app.py
```

---

### Access via WSL

If you have WSL installed, you can run the Linux version:

```bash
# In WSL terminal
cd /mnt/c/Users/YourName/mwebui/host
python3 app.py
```

Access from Windows: http://localhost:5000

---

## ✅ Tested On

- ✅ Windows 10 (22H2)
- ✅ Windows 11
- ✅ Python 3.8, 3.9, 3.10, 3.11, 3.12

---

## 🔧 Troubleshooting

### `'modal' is not recognized`

Add Python Scripts to PATH:
```cmd
set PATH=%PATH%;%APPDATA%\Python\Scripts
```

Permanently in System Environment Variables.

---

### `Permission denied` errors

Run CMD/PowerShell as Administrator.

---

### `Module not found` after pip install

Make sure venv is activated. You should see `(venv)` in prompt.

---

## 📚 Additional Resources

- **Python Windows Guide:** https://docs.python.org/3/using/windows.html
- **Modal Documentation:** https://modal.com/docs
- **Git Bash:** https://git-scm.com/download/win
- **Cloudflared Windows:** https://developers.cloudflare.com/cloudflare-one/

---

**Ready to use on Windows!** 🎉
