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

### 1. Setup Environment Variables

The `.env` file is the **Single Source of Truth** for all credentials. Create/edit the `.env` file in the `host/` folder:

```env
# Worker Authentication
DEFAULT_WORKER_TOKEN="your_default_worker_token"
WORKER_AUTH_TOKEN="your_worker_auth_token"

# GitHub & Hugging Face
GH_TOKEN="ghp_xxx"
HF_TOKEN="hf_xxx"

# Host Configuration  
API_URL="https://your-host.domain.com/heartbeat"
API_KEY="your_secret_key"

# Cloudflare Zero Trust
CF_CLIENT_ID="your_cf_client_id"
CF_CLIENT_SECRET="your_cf_client_secret"

# Cloudflare Tunnel Tokens
APP_CLOUDFLARED_TOKEN="your_app_tunnel_token"
CLOUDFLARED_TOKEN="your_modal_tunnel_token"

# SSH Key for Remote Development
SSH_KEY="ssh-ed25519 AAAA... user@hostname"
```

### 2. Deploy Secrets to Modal

Run the script to push secrets to Modal:

```bash
bash create_modal_secret.sh
```

Verify:
```bash
modal secret list
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Application

```bash
python app.py
```

The application will run at `http://0.0.0.0:5000` with Cloudflare Tunnel automatically enabled.

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

- Make sure `cloudflared` is installed for automatic tunneling
- Internal worker is automatically active when the application runs
- Default session timeout follows Flask session configuration
