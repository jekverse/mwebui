# Remote Worker Host - Modal App Manager

A Flask-based web application for centrally managing and monitoring Modal workers through an interactive web interface.

## ✨ Key Features

### 🖥️ Worker Management
- **Real-time Terminal**: Multi-session interactive terminal for each worker
- **Auto-connect Worker**: Support for internal and external workers
- **Live Status**: Real-time worker status monitoring via Socket.IO

### 📦 Modal Volume Management
- View, create, and delete Modal volumes
- Browse files within volumes
- Delete individual files from volumes

### 🎨 Image Builder (Code Editor)
- Integrated code editor for `modal-app-manager/images/`
- Create, edit, and delete image configuration files
- Python syntax highlighting

### 🔐 Profile & Authentication
- Multi-profile Modal support (`~/.modal.toml`)
- Admin sign-up flow with password protection
- Session-based authentication

### 🔄 Restore Model Script Generator
- Auto-generate scripts for restoring models from Hugging Face
- Diff directory configuration via dropdown

---

## 🚀 Quick Start

### Prerequisites

Before starting, make sure you have:
- Python 3.8 or higher
- A [Modal](https://modal.com) account
- (Optional) [Cloudflare](https://cloudflare.com) account for tunneling

---

### Step 1: Clone and Navigate

```bash
cd /path/to/gaswebui/host
```

---

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Your terminal should now show (venv) prefix
```

---

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

**Required packages:**
- `flask` - Web framework
- `flask-socketio` - Real-time communication
- `modal` - Modal Python SDK
- `eventlet` - Async server

---

### Step 4: Setup Modal Account

#### 4.1. Check Existing Configuration

```bash
cat ~/.modal.toml
```

If the file exists, you're already set up. Skip to Step 5.

#### 4.2. First-Time Modal Setup

If `~/.modal.toml` doesn't exist:

```bash
modal setup
```

This will:
1. Open your browser
2. Ask you to log in to Modal
3. Generate an API token
4. Save credentials to `~/.modal.toml`

**Example `~/.modal.toml`:**
```toml
[default]
token_id = "ak-xxx"
token_secret = "as-xxx"
```

---

### Step 5: Configure Environment Variables

The `.env` file stores all credentials and configuration. **This is required!**

#### 5.1. Create `.env` File

```bash
cd /path/to/gaswebui/host
nano .env
```

#### 5.2. Fill in Required Variables

Copy and paste this template, then replace values:

```env
# ==========================================
# WORKER AUTHENTICATION
# ==========================================
# Token for worker authentication (internal worker)
DEFAULT_WORKER_TOKEN="change_me_random_token_123"

# Alternative worker auth token (external workers)
WORKER_AUTH_TOKEN="change_me_worker_token_456"

# ==========================================
# GITHUB & HUGGING FACE
# ==========================================
# GitHub Personal Access Token (for cloning private repos)
# Get from: https://github.com/settings/tokens
GH_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Hugging Face API Token (for downloading models)
# Get from: https://huggingface.co/settings/tokens
HF_TOKEN="hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# ==========================================
# CLOUDFLARE TUNNEL TOKENS
# ==========================================
# Cloudflare Tunnel token for HOST application
# Get from: https://one.dash.cloudflare.com/
# Navigate to: Zero Trust → Networks → Tunnels → Create Tunnel
APP_CLOUDFLARED_TOKEN="eyJhIjoixxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Cloudflare Tunnel token for MODAL workers (if needed)
CLOUDFLARED_TOKEN="eyJhIjoixxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# ==========================================
# OPTIONAL: SSH KEY FOR REMOTE DEVELOPMENT
# ==========================================
# Your public SSH key (for code-server access in Modal VMs)
SSH_KEY="ssh-ed25519 AAAA..."
```

#### 5.3. Variable Descriptions

| Variable | Required | Description |
|----------|----------|-------------|
| `DEFAULT_WORKER_TOKEN` | ✅ Yes | Authentication token for internal worker |
| `WORKER_AUTH_TOKEN` | ✅ Yes | Authentication token for external workers |
| `GH_TOKEN` | ⚠️ Optional* | GitHub token for private repos (*required if using private repos) |
| `HF_TOKEN` | ⚠️ Optional* | Hugging Face token (*required for downloading models) |
| `APP_CLOUDFLARED_TOKEN` | ⚠️ Optional | Cloudflare tunnel token for public access to host |
| `CLOUDFLARED_TOKEN` | ⚠️ Optional | Cloudflare tunnel token for Modal workers |
| `SSH_KEY` | ❌ Optional | SSH public key for remote development |

#### 5.4. How to Get Tokens

**GitHub Token (GH_TOKEN):**
1. Go to https://github.com/settings/tokens
2. Click "Generate new token" → "Classic"
3. Select scopes: `repo` (for private repos)
4. Copy token (starts with `ghp_`)

**Hugging Face Token (HF_TOKEN):**
1. Go to https://huggingface.co/settings/tokens
2. Click "New token"
3. Select "Read" access
4. Copy token (starts with `hf_`)

**Cloudflare Tunnel Token:**
1. Go to https://one.dash.cloudflare.com/
2. Navigate to **Zero Trust → Networks → Tunnels**
3. Click "Create a tunnel"
4. Choose "Cloudflared"
5. Copy the tunnel token (starts with `eyJh`)

---

### Step 6: Deploy Secrets to Modal

Modal VMs need access to your tokens. Deploy them as Modal secrets:

```bash
bash create_modal_secret.sh
```

**What this does:**
- Reads `.env` file
- Creates a Modal secret named `my-secrets`
- Uploads: `GH_TOKEN`, `HF_TOKEN`, `CLOUDFLARED_TOKEN`, `SSH_KEY`

**Verify deployment:**
```bash
modal secret list
```

You should see:
```
✓ my-secrets
```

**Important:** Re-run this script whenever you update `.env`!

---

### Step 7: (Optional) Install Cloudflared

Only needed if you want public HTTPS access to your host application.

```bash
# Add Cloudflare GPG key
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-public-v2.gpg | \
  sudo tee /usr/share/keyrings/cloudflare-public-v2.gpg >/dev/null

# Add repository
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-public-v2.gpg] https://pkg.cloudflare.com/cloudflared any main' | \
  sudo tee /etc/apt/sources.list.d/cloudflared.list

# Install
sudo apt-get update && sudo apt-get install cloudflared
```

**Verify installation:**
```bash
cloudflared --version
```

---

### Step 8: Run the Application

```bash
# Make sure virtual environment is active
source venv/bin/activate

# Run the Flask app
python app.py
```

**Expected output:**
```
Initializing Internal Worker...
Starting default session-1...
Cloudflare Tunnel started with PID: xxxxx
 * Running on http://0.0.0.0:5000
```

**Access the application:**
- Local: http://localhost:5000
- LAN: http://YOUR_LOCAL_IP:5000
- Public (if Cloudflare configured): https://your-tunnel.trycloudflare.com

---

### Step 9: First-Time Login

1. Open the application in your browser
2. You'll be redirected to **Sign Up** page (first time only)
3. Create admin credentials:
   - Username: `admin` (or your choice)
   - Password: (strong password)
4. Click "Sign Up"
5. You're now logged in!

---

### Quick Troubleshooting

**Issue: `ModuleNotFoundError: No module named 'flask'`**
```bash
# Make sure venv is activated
source venv/bin/activate
pip install -r requirements.txt
```

**Issue: `modal: command not found`**
```bash
# Install Modal globally
pip install --user modal
# Add to PATH
export PATH="$HOME/.local/bin:$PATH"
```

**Issue: `Cloudflare Tunnel failed to start`**
- Check `APP_CLOUDFLARED_TOKEN` in `.env`
- Make sure `cloudflared` is installed
- Or disable tunnel: comment out tunnel code in `app.py`

**Issue: Modal secrets not found**
```bash
# Re-run secret deployment
bash create_modal_secret.sh
modal secret list
```

---

## 📁 Folder Structure

```
host/
├── app.py                    # Main Flask application
├── internal_worker.py        # Internal worker implementation
├── auth.json                 # Auth configuration (auto-generated)
├── .env                      # Environment variables
├── create_modal_secret.sh    # Script to deploy secrets to Modal
├── requirements.txt          # Python dependencies
├── modal-app-manager/
│   └── images/               # Image configurations
│       ├── app.py            # Modal app entrypoint
│       ├── base_image.py     # Base image definition
│       └── restore_model/    # Restore model scripts
├── templates/
│   ├── index.html            # Main dashboard
│   ├── login.html            # Login page
│   └── signup.html           # Sign-up page
└── static/
    └── uploads/avatars/      # User avatar uploads
```

---

## 🔧 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard |
| `/login` | GET/POST | Login page |
| `/signup` | GET/POST | Sign-up page (first-time setup) |
| `/heartbeat` | POST | Worker heartbeat endpoint |
| `/api/fs/*` | GET/POST | File system API (code editor) |
| `/api/volumes` | GET | List Modal volumes |
| `/api/volumes/create` | POST | Create Modal volume |
| `/api/volumes/delete` | POST | Delete Modal volume |
| `/api/volumes/files` | GET | List volume files |
| `/api/generate-restore-script` | POST | Generate restore script |
| `/api/config/profile` | POST | Add Modal profile |
| `/api/config/profile/delete` | POST | Delete Modal profile |

---

## 🔐 First-Time Setup

1. Access the application and you will be redirected to the **Sign Up** page
2. Create an admin username and password
3. After logging in, you can:
   - Add Modal profiles via Settings
   - Manage workers and volumes
   - Use the code editor for image configurations

---

## 📝 Notes

- Always activate virtual environment before running: `source venv/bin/activate`
- Run `bash create_modal_secret.sh` after changing `.env` to update Modal secrets
- Internal worker is automatically active when the application runs
- Default session timeout follows Flask session configuration
