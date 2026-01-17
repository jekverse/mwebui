import eventlet
import warnings
warnings.simplefilter('ignore')
eventlet.monkey_patch()

import os
import uuid
import sys
import subprocess
import atexit
import functools
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import socketio as sio_client
import requests
import shutil
import json
import re
from dotenv import load_dotenv
from internal_worker import InternalWorker

load_dotenv()

import logging

# Suppress verbose socketio/engineio logs
logging.getLogger('socketio').setLevel(logging.ERROR)
logging.getLogger('engineio').setLevel(logging.ERROR)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret!')
# Disable default logger in SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', logger=False, engineio_logger=False)

# GPU Rates for Heartbeat
GPU_RATES = {
    "Nvidia B200": 6.75, "Nvidia H200": 5.04, "Nvidia H100": 4.45,
    "Nvidia A100, 80 GB": 3.00, "Nvidia A100, 40 GB": 2.60,
    "Nvidia L40S": 2.45, "Nvidia A10": 1.60, "Nvidia L4": 1.30, "Nvidia T4": 1.09,
    "CPU": 0.1
}

# Internal Worker Instance
local_worker = None
local_worker_id = 'local-internal'

# Dictionary to store worker connections
# Format: { worker_id: { 'client': socketio.Client(), 'url': str, 'status': str, 'sessions': {}, 'closed_sessions': set() } }
workers = {}

# --- CLOUDFLARE TUNNEL ---
tunnel_process = None

def cleanup_tunnel():
    global tunnel_process
    if tunnel_process:
        print(f"Stopping Cloudflare Tunnel (PID: {tunnel_process.pid})...")
        tunnel_process.terminate()
        try:
            tunnel_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tunnel_process.kill()
        print("Cloudflare Tunnel stopped.")

def start_tunnel():
    global tunnel_process
    token = os.getenv('APP_CLOUDFLARED_TOKEN')
    if not token:
        print("Warning: APP_CLOUDFLARED_TOKEN not set in environment.")
        return
    cmd = ["cloudflared", "tunnel", "run", "--token", token]
    
    try:
        print("Starting Cloudflare Tunnel...")
        # Run in background
        tunnel_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Cloudflare Tunnel started with PID: {tunnel_process.pid}")
        atexit.register(cleanup_tunnel)
    except Exception as e:
        print(f"Failed to start Cloudflare Tunnel: {e}")

def on_worker_output(worker_id, data):
    """Callback for when a worker sends output."""
    output = data.get('output')
    session_id = data.get('session_id')
    
    # Check if session is explicitly closed (Zombie protection)
    if worker_id in workers and 'closed_sessions' in workers[worker_id]:
        if session_id in workers[worker_id]['closed_sessions']:
            return # Ignore output from closed session
    
    # Store log per session
    if worker_id in workers:
        if 'sessions' not in workers[worker_id]:
            workers[worker_id]['sessions'] = {}
            
        # If session_id is missing (legacy/error), maybe map to 'session-1' or ignore?
        # For now, let's assume session_id is present or default to 'session-1'
        target_session = session_id or 'session-1'
        
        if target_session not in workers[worker_id]['sessions']:
             workers[worker_id]['sessions'][target_session] = {'logs': []}
             
        workers[worker_id]['sessions'][target_session]['logs'].append(output)
        
    # Forward to UI with worker_id so UI knows which terminal to update
    socketio.emit('term_output', {'worker_id': worker_id, 'session_id': session_id, 'output': output})

def on_worker_connect(worker_id):
    """Callback for when a worker connects."""
    # print(f"Worker {worker_id} connected")
    if worker_id in workers:
        workers[worker_id]['status'] = 'connected'
        socketio.emit('worker_status', {'worker_id': worker_id, 'status': 'connected'})

def on_worker_disconnect(worker_id):
    """Callback for when a worker disconnects."""
    # print(f"Worker {worker_id} disconnected")
    if worker_id in workers:
        workers[worker_id]['status'] = 'disconnected'
        socketio.emit('worker_status', {'worker_id': worker_id, 'status': 'disconnected'})


import datetime
import json
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from flask import session, redirect, url_for, flash, abort, g

# Auth Configuration Class
class ConfigManager:
    CONFIG_FILE = 'auth.json'
    
    @classmethod
    def load_config(cls):
        if not os.path.exists(cls.CONFIG_FILE):
             return None # No config yet
        try:
            with open(cls.CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading auth config: {e}")
            return None

    @classmethod
    def save_config(cls, config):
        try:
            with open(cls.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving auth config: {e}")
            return False

    @classmethod
    def get_default(cls):
        # Default fallback
        return {
            "username": "admin",
            "password_hash": generate_password_hash("admin"),
            "avatar_url": "https://api.dicebear.com/7.x/avataaars/svg?seed=admin"
        }

    # Migration logic removed


    @classmethod
    def is_initialized(cls):
        return os.path.exists(cls.CONFIG_FILE)

    @classmethod
    def verify_password(cls, password):
        config = cls.load_config()
        if not config: return False
        return check_password_hash(config['password_hash'], password)

    @classmethod
    def update_password(cls, new_password):
        config = cls.load_config()
        config['password_hash'] = generate_password_hash(new_password)
        return cls.save_config(config)

    @classmethod
    def update_profile(cls, username=None, avatar_url=None):
        config = cls.load_config()
        if username: config['username'] = username
        if avatar_url: config['avatar_url'] = avatar_url
        return cls.save_config(config)

# Upload Config
UPLOAD_FOLDER = 'static/uploads/avatars'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Ensure upload dir exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Rate Limiting (In-Memory)
login_attempts = {}
MAX_ATTEMPTS = 3
BLOCK_DURATION = datetime.timedelta(minutes=5)

@app.before_request
@app.before_request
def require_login():
    """Protect all routes except login, signup, static files, and heartbeat."""
    allowed_endpoints = ['login', 'signup', 'static', 'proxy_heartbeat']
    
    # 1. Check if system is initialized
    if not ConfigManager.is_initialized():
        if request.endpoint != 'signup' and request.endpoint != 'static':
            return redirect(url_for('signup'))
        return # Allow access to signup
        
    # 2. If initialized, prevent access to signup
    if request.endpoint == 'signup':
        return redirect(url_for('login'))

    # 3. Require login for protected routes
    if request.endpoint not in allowed_endpoints and 'authenticated' not in session:
        return redirect(url_for('login'))

@app.context_processor
def inject_user():
    if 'authenticated' in session:
        config = ConfigManager.load_config()
        return dict(current_user=config)
    return dict(current_user=None)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ip = request.remote_addr
        now = datetime.datetime.now()
        
        # Check Rate Limit
        if ip in login_attempts:
            record = login_attempts[ip]
            if record['block_until'] and now < record['block_until']:
                remaining = (record['block_until'] - now).seconds
                return render_template('login.html', error=f"Too many attempts. Try again in {remaining}s.")
            
            if record['block_until'] and now > record['block_until']:
                 record['count'] = 0
                 record['block_until'] = None

        username_input = request.form.get('username')
        password_input = request.form.get('password')
        
        config = ConfigManager.load_config()
        
        # Verify Username AND Password
        # Compare Username (case insensitive)
        is_username_valid = username_input and username_input.lower() == config.get('username', 'admin').lower()
        is_password_valid = check_password_hash(config['password_hash'], password_input) if password_input else False

        if is_username_valid and is_password_valid:
            # Success
            session['authenticated'] = True
            session.permanent = True
            if ip in login_attempts:
                del login_attempts[ip]
            return redirect(url_for('index'))
        else:
            # Failure
            if ip not in login_attempts:
                login_attempts[ip] = {'count': 0, 'block_until': None}
            
            login_attempts[ip]['count'] += 1
            
            if login_attempts[ip]['count'] >= MAX_ATTEMPTS:
                login_attempts[ip]['block_until'] = now + BLOCK_DURATION
                return render_template('login.html', error="Too many attempts. blocked for 5 minutes.")
            
            remaining = MAX_ATTEMPTS - login_attempts[ip]['count']
            return render_template('login.html', error=f"Invalid credentials. {remaining} attempts remaining.")

    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not username or not password:
             return render_template('signup.html', error="Username and password required")
             
        if password != confirm_password:
             return render_template('signup.html', error="Passwords do not match")
             
        # Create Config
        config = {
            "username": username,
            "password_hash": generate_password_hash(password),
            "avatar_url": f"https://api.dicebear.com/7.x/avataaars/svg?seed={username}"
        }
        
        if ConfigManager.save_config(config):
            flash("Account created! Please login.")
            return redirect(url_for('login'))
        else:
             return render_template('signup.html', error="Failed to save configuration")
             
    return render_template('signup.html')

@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    # Handle Form Data
    username = request.form.get('username')
    
    # Handle File Upload
    avatar_url = None
    if 'avatar' in request.files:
        file = request.files['avatar']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(f"{uuid.uuid4().hex[:8]}_{file.filename}")
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            # URL relative to static
            avatar_url = f"/{filepath}"
    
    if ConfigManager.update_profile(username, avatar_url):
        return jsonify({'status': 'success', 'avatar_url': avatar_url})
    return jsonify({'error': 'Failed to save'}), 500

@app.route('/api/profile/password', methods=['POST'])
def update_password():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    current_pass = data.get('current_password')
    new_pass = data.get('new_password')
    
    config = ConfigManager.load_config()
    
    if not check_password_hash(config['password_hash'], current_pass):
        return jsonify({'error': 'Incorrect current password'}), 400
        
    if ConfigManager.update_password(new_pass):
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Failed to save'}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- File System API (Simple Code Editor) ---
API_FS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modal-app-manager', 'images')

@app.route('/api/fs/list')
def fs_list():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    target_path = request.args.get('path', '')
    
    # Security check: join path and check if it starts with ROOT
    abs_root = os.path.abspath(API_FS_ROOT)
    safe_path = os.path.abspath(os.path.join(abs_root, target_path))
    
    if not safe_path.startswith(abs_root):
        return jsonify({'error': 'Invalid path'}), 400
        
    if not os.path.exists(safe_path):
        return jsonify({'error': 'Path not found'}), 404
    
    try:
        files = []
        
        # Simple flat list for now, or maybe just listdir
        # Let's filter for .py, .txt, .json, .md, .html, .css, .js, .sh
        allowed_exts = {'.py', '.txt', '.json', '.md', '.html', '.css', '.js', '.sh', '.yaml', '.yml', '.env'}
        
        for f in os.listdir(safe_path):
            full_path = os.path.join(safe_path, f)
            rel_path = os.path.relpath(full_path, abs_root) # Get path relative to API_FS_ROOT for frontend
            
            if os.path.isfile(full_path):
                ext = os.path.splitext(f)[1].lower()
                if ext in allowed_exts or f.startswith('.'): # Allow dotfiles like .env
                    files.append({
                        'name': f,
                        'path': rel_path, 
                        'type': 'file',
                        'size': os.path.getsize(full_path)
                    })
            elif os.path.isdir(full_path):
                 files.append({
                    'name': f,
                    'path': rel_path,
                    'type': 'directory',
                    'size': 0
                 })
        
        # Sort by type (dirs first) then name
        files.sort(key=lambda x: (x['type'] != 'directory', x['name']))
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/fs/read')
def fs_read():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    target_path = request.args.get('path')
    if not target_path: return jsonify({'error': 'No path provided'}), 400
    
    # Security check: join path and check if it starts with ROOT
    abs_root = os.path.abspath(API_FS_ROOT)
    # Join root with the provided relative path
    safe_path = os.path.abspath(os.path.join(abs_root, target_path))
    
    # Check for path traversal
    if not safe_path.startswith(abs_root):
        return jsonify({'error': 'Invalid path'}), 400
    
    if not os.path.exists(safe_path) or not os.path.isfile(safe_path):
        return jsonify({'error': 'File not found'}), 404
        
    try:
        with open(safe_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'content': content})
        

    except Exception as e:
         return jsonify({'error': str(e)}), 500

@app.route('/api/fs/save', methods=['POST'])
def fs_save():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    target_path = data.get('path')
    content = data.get('content')
    
    if not target_path: return jsonify({'error': 'No path provided'}), 400
    if content is None: return jsonify({'error': 'No content provided'}), 400
    
    # Security check
    abs_root = os.path.abspath(API_FS_ROOT)
    safe_path = os.path.abspath(os.path.join(abs_root, target_path))
    
    if not safe_path.startswith(abs_root):
        return jsonify({'error': 'Invalid path'}), 400

    try:
        # Create parent directories if they don't exist
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'status': 'success'})
    except Exception as e:
         return jsonify({'error': str(e)}), 500

@app.route('/api/fs/create', methods=['POST'])
def fs_create():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    path = data.get('path')
    item_type = data.get('type') # 'file' or 'directory'
    
    if not path: return jsonify({'error': 'No path provided'}), 400
    
    # Security check: join path and check if it starts with ROOT
    abs_root = os.path.abspath(API_FS_ROOT)
    # Join root with the provided relative path
    safe_path = os.path.abspath(os.path.join(abs_root, path))
    
    # Check for path traversal
    if not safe_path.startswith(abs_root):
        return jsonify({'error': 'Invalid path'}), 400
    
    if os.path.exists(safe_path):
        return jsonify({'error': 'Item already exists'}), 400
        
    try:
        # Ensure parent directory exists
        parent_dir = os.path.dirname(safe_path)
        if not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        if item_type == 'directory':
            os.makedirs(safe_path)
        else:
            with open(safe_path, 'w') as f:
                f.write('') # Create empty file
                
        return jsonify({'status': 'success'})
    except Exception as e:
         return jsonify({'error': str(e)}), 500

@app.route('/api/config/add_profile', methods=['POST'])
def config_add_profile():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    config_text = data.get('config_text')
    
    if not config_text or not config_text.strip():
        return jsonify({'error': 'Config text is required'}), 400
        
    # Basic security check for duplicates or obviously bad input?
    # For now we trust the text, but ensure newline separation
    
    modal_config_path = os.path.expanduser('~/.modal.toml')
    
    try:
        # Append to file with ensuring newlines
        with open(modal_config_path, 'a') as f:
            f.write(f"\n{config_text.strip()}\n")
            
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/config/delete_profile', methods=['POST'])
def config_delete_profile():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    profile_name = data.get('profile_name')
    
    if not profile_name:
        return jsonify({'error': 'Profile name is required'}), 400
        
    modal_config_path = os.path.expanduser('~/.modal.toml')
    if not os.path.exists(modal_config_path):
         return jsonify({'error': 'Config file not found'}), 404
         
    try:
        with open(modal_config_path, 'r') as f:
            lines = f.readlines()
            
        new_lines = []
        skip_block = False
        deleted = False
        
        for line in lines:
            stripped = line.strip()
            # Check for profile start
            if stripped.startswith('[') and stripped.endswith(']'):
                current_profile = stripped[1:-1]
                if current_profile == profile_name:
                    skip_block = True
                    deleted = True
                else:
                    skip_block = False
            
            if not skip_block:
                new_lines.append(line)
        
        if not deleted:
             return jsonify({'error': 'Profile not found'}), 404
             
        with open(modal_config_path, 'w') as f:
            f.writelines(new_lines)
            
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    data = request.json
    old_rel_path = data.get('old_path')
    new_rel_path = data.get('new_path')
    
    if not old_rel_path or not new_rel_path:
        return jsonify({'error': 'Missing paths'}), 400
        
    abs_root = os.path.abspath(API_FS_ROOT)
    # Join root with provided paths
    safe_old = os.path.abspath(os.path.join(abs_root, old_rel_path))
    safe_new = os.path.abspath(os.path.join(abs_root, new_rel_path))
    
    # Check traversal
    if not safe_old.startswith(abs_root) or not safe_new.startswith(abs_root):
        return jsonify({'error': 'Invalid path'}), 400
        
    if not os.path.exists(safe_old):
        return jsonify({'error': 'Item not found'}), 404
    if os.path.exists(safe_new):
        return jsonify({'error': 'Destination already exists'}), 400
        
    try:
        os.rename(safe_old, safe_new)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/fs/delete', methods=['POST'])
def fs_delete():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    rel_path = data.get('path')
    
    if not rel_path:
        return jsonify({'error': 'No path provided'}), 400
        
    abs_root = os.path.abspath(API_FS_ROOT)
    safe_path = os.path.abspath(os.path.join(abs_root, rel_path))
    
    if not safe_path.startswith(abs_root):
        return jsonify({'error': 'Invalid path'}), 400
        
    if not os.path.exists(safe_path):
        return jsonify({'error': 'Item not found'}), 404
        
    try:
        if os.path.isdir(safe_path):
            import shutil
            shutil.rmtree(safe_path)
        else:
            os.remove(safe_path)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    host_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Dynamic Paths
    work_dir = os.path.join(host_dir, 'modal-app-manager', 'images')
    wallet_dir = os.path.join(host_dir, 'modal-credit-tracker')
    
    # Find modal binary (check PATH, fallback to default locations)
    modal_bin = shutil.which('modal') or os.path.expanduser('~/.local/bin/modal')
    
    return render_template('index.html', 
                         work_dir=work_dir, 
                         modal_bin=modal_bin,
                         wallet_dir=wallet_dir)

@app.route('/heartbeat', methods=['POST'])
def proxy_heartbeat():
    # Handle heartbeat directly using InternalWorker logic
    if not local_worker:
         return jsonify({"detail": "Local Worker Not Initialized"}), 500
         
    # 1. Verify API Key
    api_key = request.headers.get('x-api-key')
    # Use same key or bypass since it's internal? Let's check against env
    expected_key = os.getenv('API_KEY')
    if api_key != expected_key:
          return jsonify({"detail": "Akses Ditolak: API Key Salah"}), 403
          
    data = request.get_json(silent=True)
    if not data:
         return jsonify({"detail": "Invalid JSON"}), 400
         
    account_name = data.get('account_name')
    gpu_type = data.get('gpu_type')
    session_id = data.get('session_id')
    
    if not account_name or not gpu_type:
          return jsonify({"detail": "Missing status fields"}), 422 

    # Process via Internal Worker
    resp_data, status_code = local_worker.process_heartbeat_logic(account_name, gpu_type, GPU_RATES, session_id)
    return jsonify(resp_data), status_code

@socketio.on('connect')
def handle_connect():
    if 'authenticated' not in session:
        print("Rejected unauthenticated socket connection")
        return False  # Reject connection
    print("Client connected to Host")
    # Send existing workers to the new client
    for wid, wdata in workers.items():
        # Prepare sessions data
        sessions_data = {}
        for sid, sdata in wdata.get('sessions', {}).items():
            sessions_data[sid] = {
                'logs': "".join(sdata['logs'])
            }
            
        emit('worker_added', {
            'worker_id': wid, 
            'url': wdata['url'], 
            'name': wdata.get('name', wdata['url']),
            'token': wdata.get('token', ''),
            'status': wdata['status'],
            'sessions': sessions_data # Send all sessions
        })

@socketio.on('remove_worker')
def handle_remove_worker(data):
    worker_id = data.get('worker_id')
    if worker_id in workers:
        print(f"Removing worker: {worker_id}")
        # Disconnect client
        try:
            workers[worker_id]['client'].disconnect()
        except:
            pass
        del workers[worker_id]
        emit('worker_removed', {'worker_id': worker_id})

# --- Modal Volume API ---
@app.route('/api/modal/volumes')
def get_modal_volumes():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Use full path to modal if known, or rely on PATH
        modal_bin = shutil.which('modal') or os.path.expanduser('~/.local/bin/modal')
        
        # Run: modal volume list --json
        cmd = [modal_bin, 'volume', 'list', '--json']
        
        # Execute
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        volumes = json.loads(result)
        
        return jsonify({'volumes': volumes})
    except subprocess.CalledProcessError as e:
        print(f"Error fetching volumes: {e.output.decode()}")
        return jsonify({'error': 'Failed to fetch volumes', 'details': e.output.decode()}), 500
    except Exception as e:
        print(f"Error executing modal command: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/modal/volume/delete', methods=['POST'])
def delete_modal_volume():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    vol_name = data.get('name')
    if not vol_name:
        return jsonify({'error': 'Volume name required'}), 400

    try:
        modal_bin = shutil.which('modal') or os.path.expanduser('~/.local/bin/modal')
        
        # Run: modal volume delete <name>
        # We need to pipe 'y' to confirm deletion
        cmd = [modal_bin, 'volume', 'delete', vol_name]
        
        process = subprocess.Popen(
            cmd, 
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input='y\n')
        
        if process.returncode != 0:
            print(f"Error deleting volume: {stderr}")
            return jsonify({'error': 'Failed to delete volume', 'details': stderr}), 500
            
        return jsonify({'status': 'success', 'output': stdout})
        
    except Exception as e:
        print(f"Error executing modal delete: {e}")
        return jsonify({'error': str(e)}), 500

# --- Restore Model Script Generation ---
@app.route('/api/restore-model/generate', methods=['POST'])
def generate_restore_script():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    filename = data.get('filename')
    items = data.get('items', [])
    
    if not filename:
        return jsonify({'error': 'Filename is required'}), 400
    if not filename.endswith('.py'):
        filename += '.py'
        
    # Sanitize variable name
    var_name = re.sub(r'[\s-]', '_', filename.replace('.py', ''))
    var_name = re.sub(r'[^\w]', '', var_name)
    
    # Title
    app_title = filename.replace('.py', '').upper()
    
    # Construct Content
    py_content = f"# filename: {filename}\n"
    py_content += "from downloader_base import create_downloader_app, MODELS_BASE_PATH\n\n"
    
    py_content += f"{var_name} = [\n"
    
    for item in items:
        url = item.get('url', '').strip()
        directory = item.get('directory', '').strip()
        
        if url:
             py_content += "    {\n"
             py_content += f'        "url": "{url}",\n'
             # Handle directory: if it's just a folder name like "checkpoints", append to base path
             # If user typed full path? Let's assume relative to MODELS_BASE_PATH like dmaker
             # dmaker logic: "directory": f"{MODELS_BASE_PATH}/{directory}"
             
             # Clean directory string
             directory = directory.strip('/')
             py_content += f'        "directory": f"{{MODELS_BASE_PATH}}/{directory}"\n'
             py_content += "    },\n"
             
    py_content += "]\n\n"
    py_content += f'app = create_downloader_app("{app_title}", {var_name})'
    
    # Save File
    restore_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modal-app-manager', 'images', 'restore_model')
    os.makedirs(restore_dir, exist_ok=True)
    
    file_path = os.path.join(restore_dir, filename)
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(py_content)
        return jsonify({'status': 'success', 'filename': filename})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/modal/volume/create', methods=['POST'])
def create_modal_volume():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    vol_name = data.get('name')
    if not vol_name:
        return jsonify({'error': 'Volume name required'}), 400
        
    # Basic validation
    if not re.match(r'^[a-zA-Z0-9_\-]+$', vol_name):
         return jsonify({'error': 'Invalid volume name. Use only letters, numbers, underscores, and dashes.'}), 400

    try:
        modal_bin = shutil.which('modal') or os.path.expanduser('~/.local/bin/modal')
        
        # Run: modal volume create <name>
        cmd = [modal_bin, 'volume', 'create', vol_name]
        
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            print(f"Error creating volume: {stderr}")
            return jsonify({'error': 'Failed to create volume', 'details': stderr}), 500
            
        return jsonify({'status': 'success', 'output': stdout})
        
    except Exception as e:
        print(f"Error executing modal create: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/modal/volume/files', methods=['POST'])
def get_modal_volume_files():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    vol_name = data.get('name')
    path = data.get('path', '/')
    
    if not vol_name:
        return jsonify({'error': 'Volume name required'}), 400

    try:
        modal_bin = shutil.which('modal') or os.path.expanduser('~/.local/bin/modal')
        
        # Run: modal volume ls <name> <path> --json
        cmd = [modal_bin, 'volume', 'ls', vol_name, path, '--json']
        
        # Execute
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        files = json.loads(result)
        
        return jsonify({'files': files, 'path': path})
    except subprocess.CalledProcessError as e:
        print(f"Error fetching volume files: {e.output.decode()}")
        return jsonify({'error': 'Failed to fetch files', 'details': e.output.decode()}), 500
    except Exception as e:
        print(f"Error executing modal command: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/modal/volume/rm', methods=['POST'])
def remove_modal_volume_file():
    if 'authenticated' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    vol_name = data.get('volume_name')
    path = data.get('path')
    
    if not vol_name or not path:
        return jsonify({'error': 'Volume name and path required'}), 400

    try:
        modal_bin = shutil.which('modal') or os.path.expanduser('~/.local/bin/modal')
        
        # Run: modal volume rm <volume_name> <path>
        cmd = [modal_bin, 'volume', 'rm', vol_name, path]
        
        process = subprocess.Popen(
            cmd, 
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input='y\n')
        
        if process.returncode != 0:
            print(f"Error deleting file: {stderr}")
            return jsonify({'error': 'Failed to delete file', 'details': stderr}), 500
            
        return jsonify({'status': 'success', 'output': stdout})
        
    except Exception as e:
        print(f"Error executing modal rm: {e}")
        return jsonify({'error': str(e)}), 500

@socketio.on('update_worker')
def handle_update_worker(data):
    worker_id = data.get('worker_id')
    name = data.get('name')
    url = data.get('url')
    token = data.get('token')

    if worker_id in workers:
        print(f"Updating worker {worker_id}: Name={name}, URL={url}")
        worker = workers[worker_id]
        
        # Update metadata
        worker['name'] = name
        
        # Check if connection details changed
        reconnect_needed = False
        if url and url != worker['url']:
            worker['url'] = url
            reconnect_needed = True
        
        if token is not None and token != worker.get('token'):
            worker['token'] = token
            reconnect_needed = True
            
        # Notify UI of update
        emit('worker_updated', {
            'worker_id': worker_id,
            'name': worker['name'],
            'url': worker['url'],
            'token': worker.get('token', ''),
            'status': worker['status'] # Status might change if reconnecting
        })

        if reconnect_needed:
            print(f"Reconnecting worker {worker_id} due to settings change...")
            # Disconnect existing
            try:
                worker['client'].disconnect()
            except:
                pass
            
            worker['status'] = 'connecting'
            emit('worker_status', {'worker_id': worker_id, 'status': 'connecting'})
            
            # Reconnect with new details
            socketio.start_background_task(functools.partial(connect_worker, worker_id))

@socketio.on('clear_logs')
def handle_clear_logs(data):
    worker_id = data.get('worker_id')
    session_id = data.get('session_id')
    
    if worker_id in workers:
        if session_id and session_id in workers[worker_id].get('sessions', {}):
            workers[worker_id]['sessions'][session_id]['logs'] = []
            print(f"Logs cleared for {worker_id} session {session_id}")

def connect_worker(worker_id):
    """Helper to connect a worker."""
    if worker_id not in workers:
        return

    wdata = workers[worker_id]
    url = wdata['url']
    token = wdata.get('token') or os.getenv('DEFAULT_WORKER_TOKEN', 'default-secret-key')
    client = wdata['client']

    try:
        print(f"Connecting to {url} with token: {token}")
        client.connect(url, auth={'token': token})
    except Exception as e:
        error_msg = str(e)
        if "Already connected" in error_msg or "Connection refused" in error_msg:
             # If "Already connected", just mark as connected and return
             if "Already connected" in error_msg:
                 print(f"Worker {worker_id} already connected.")
                 if worker_id in workers:
                     workers[worker_id]['status'] = 'connected'
                     socketio.emit('worker_status', {'worker_id': worker_id, 'status': 'connected'})
                 return
        
        print(f"Failed to connect to {url}: {e}")
        socketio.emit('worker_status', {'worker_id': worker_id, 'status': 'error', 'error': str(e)})
        
        # If this is the default local worker, keep retrying in background
        if url == 'http://localhost:5002':
            print(f"Retrying connection to default worker {url} in 2 seconds...")
            socketio.sleep(2)
            socketio.start_background_task(functools.partial(connect_worker, worker_id))

@socketio.on('add_worker')
def register_worker(url, name=None, token=None):
    """Registers a new worker and starts connection."""
    name = name or url
    
    # Check if URL already exists
    for wid, wdata in workers.items():
        if wdata['url'] == url:
            return wid

    # Generate a unique ID
    worker_id = str(uuid.uuid4())
    print(f"Adding worker: {url} (ID: {worker_id})")
    
    # Create new SocketIO client
    client = sio_client.Client()
    
    # Bind events with partial to pass worker_id
    client.on('output', functools.partial(on_worker_output, worker_id))
    client.on('term_output', functools.partial(on_worker_output, worker_id))
    client.on('connect', functools.partial(on_worker_connect, worker_id))
    client.on('disconnect', functools.partial(on_worker_disconnect, worker_id))
    
    # Forward session events
    def on_session_created(wid, data):
        sid = data.get('session_id')
        if wid in workers:
            if 'sessions' not in workers[wid]:
                workers[wid]['sessions'] = {}
            if sid not in workers[wid]['sessions']:
                workers[wid]['sessions'][sid] = {'logs': []}
        socketio.emit('session_created', {'worker_id': wid, 'session_id': sid})
        
    def on_session_closed(wid, data):
        sid = data.get('session_id')
        if wid in workers and 'sessions' in workers[wid]:
            if sid in workers[wid]['sessions']:
                del workers[wid]['sessions'][sid]
        socketio.emit('session_closed', {'worker_id': wid, 'session_id': sid})

    def on_exec_result(wid, data):
        data['worker_id'] = wid
        socketio.emit('exec_result', data)

    client.on('session_created', functools.partial(on_session_created, worker_id))
    client.on('session_closed', functools.partial(on_session_closed, worker_id))
    client.on('exec_result', functools.partial(on_exec_result, worker_id))
    
    workers[worker_id] = {
        'client': client,
        'url': url,
        'name': name,
        'token': token,
        'status': 'connecting',
        'sessions': {},
        'closed_sessions': set()
    }
    
    # Connect in background
    socketio.start_background_task(functools.partial(connect_worker, worker_id))
    return worker_id

@socketio.on('add_worker')
def handle_add_worker(data):
    url = data.get('url')
    name = data.get('name')
    token = data.get('token')

    if not url:
        return
    
    worker_id = register_worker(url, name, token)
    
    if worker_id in workers:
        wdata = workers[worker_id]
        # Notify UI that a new worker is being added
        emit('worker_added', {
            'worker_id': worker_id, 
            'url': wdata['url'], 
            'name': wdata['name'],
            'token': wdata.get('token', ''),
            'status': wdata['status'], 
            'sessions': {}
        })

@socketio.on('send_command')
def handle_command(data):
    worker_id = data.get('worker_id')
    session_id = data.get('session_id')
    cmd = data.get('cmd')
    
    if worker_id in workers:
        w = workers[worker_id]
        if w.get('type') == 'internal':
             # Internal workers don't support 'send_command' usually (it was for remote control events)
             # But if they do, we'd add logic to InternalWorker. For PTY, we use term_input.
             pass
        elif w['status'] == 'connected':
            print(f"Sending command to {worker_id} (Session {session_id}): {cmd}")
            w['client'].emit('command', {'cmd': cmd, 'session_id': session_id})
    else:
        emit('term_output', {'worker_id': worker_id, 'session_id': session_id, 'output': 'Error: Worker not connected\n'})

@socketio.on('get_tunnel_status')
def handle_tunnel_status():
    global tunnel_process
    is_active = tunnel_process is not None and tunnel_process.poll() is None
    emit('tunnel_status', {'active': is_active})

@socketio.on('term_input')
def handle_term_input(data):
    worker_id = data.get('worker_id')
    session_id = data.get('session_id')
    input_data = data.get('input')
    
    if worker_id in workers and workers[worker_id]['status'] == 'connected':
        if workers[worker_id].get('type') == 'internal':
             local_worker.write_input(session_id, input_data)
        else:
             workers[worker_id]['client'].emit('term_input', {'input': input_data, 'session_id': session_id})

@socketio.on('exec_command')
def handle_exec_command(data):
    worker_id = data.get('worker_id')
    cmd = data.get('command')
    cwd = data.get('cwd')
    request_id = data.get('id')
    
    if worker_id in workers:
         if workers[worker_id].get('type') == 'internal':
             print(f"Internal Exec: {cmd} (CWD: {cwd})")
             local_worker.exec_command(cmd, cwd, request_id)
         elif workers[worker_id]['status'] == 'connected':
             client = workers[worker_id]['client']
             try:
                client.emit('exec_command', {'command': cmd, 'cwd': cwd, 'id': request_id})
             except Exception as e:
                print(f"Failed to emit exec_command: {e}")
                emit('exec_result', {'id': request_id, 'worker_id': worker_id, 'stdout': '', 'stderr': f'Emit Failed: {str(e)}', 'returncode': -1})
         else:
             emit('exec_result', {'id': request_id, 'worker_id': worker_id, 'stdout': '', 'stderr': 'Worker not connected', 'returncode': -1})
    else:
        emit('exec_result', {'id': request_id, 'worker_id': worker_id, 'stdout': '', 'stderr': 'Worker not found', 'returncode': -1})

@socketio.on('get_balance')
def handle_get_balance(data):
    worker_id = data.get('worker_id')
    account_name = data.get('account_name')
    request_id = data.get('id')
    
    if worker_id in workers:
        if workers[worker_id].get('type') == 'internal':
             local_worker.get_balance(account_name, request_id)
        elif workers[worker_id]['status'] == 'connected':
             client = workers[worker_id]['client']
             print(f"Get balance on {worker_id}: {account_name} (Connected: {client.connected})")
             try:
                client.emit('get_balance', {'account_name': account_name, 'id': request_id})
             except Exception as e:
                print(f"Failed to emit get_balance: {e}")
                emit('exec_result', {'id': request_id, 'worker_id': worker_id, 'stdout': '', 'stderr': f'Emit Failed: {str(e)}', 'returncode': -1})
        else:
             print(f"Balance check blocked: Worker {worker_id} disconnected")
             emit('exec_result', {'id': request_id, 'worker_id': worker_id, 'stdout': '', 'stderr': 'Worker not connected', 'returncode': -1})

@socketio.on('resize')
def handle_resize(data):
    worker_id = data.get('worker_id')
    session_id = data.get('session_id')
    cols = data.get('cols')
    rows = data.get('rows')
    
    if worker_id in workers and workers[worker_id]['status'] == 'connected':
        if workers[worker_id].get('type') == 'internal':
            local_worker.resize(session_id, cols, rows)
        else:
            workers[worker_id]['client'].emit('resize', {'cols': cols, 'rows': rows, 'session_id': session_id})

@socketio.on('send_signal')
def handle_signal(data):
    worker_id = data.get('worker_id')
    session_id = data.get('session_id')
    signal_type = data.get('signal')
    
    if worker_id in workers and workers[worker_id]['status'] == 'connected':
         if workers[worker_id].get('type') == 'internal':
             pass # Internal workers don't support signals yet? or we should add them.
         else:
             print(f"Sending signal to {worker_id} (Session {session_id}): {signal_type}")
             workers[worker_id]['client'].emit('send_signal', {'signal': signal_type, 'session_id': session_id})

@socketio.on('create_session')
def handle_create_session(data):
    worker_id = data.get('worker_id')
    session_id = data.get('session_id')
    
    if worker_id in workers and workers[worker_id]['status'] == 'connected':
        print(f"Requesting session {session_id} on worker {worker_id}")
        if workers[worker_id].get('type') == 'internal':
             local_worker.create_session(session_id)
             # Replay history for this specific client to ensure seamless shared session
             history = local_worker.get_history(session_id)
             if history:
                 emit('term_output', {'session_id': session_id, 'output': history}, room=request.sid)
        else:
             workers[worker_id]['client'].emit('create_session', {'session_id': session_id})

@socketio.on('close_session')
def handle_close_session(data):
    worker_id = data.get('worker_id')
    session_id = data.get('session_id')
    
    if worker_id in workers:
        # Remove from backend state immediately to fix persistence bug
        if 'sessions' in workers[worker_id] and session_id in workers[worker_id]['sessions']:
            del workers[worker_id]['sessions'][session_id]
            print(f"Removed session {session_id} from worker {worker_id} state")
            
        # Add to closed_sessions to prevent resurrection
        if 'closed_sessions' not in workers[worker_id]:
             workers[worker_id]['closed_sessions'] = set()
        workers[worker_id]['closed_sessions'].add(session_id)

        if workers[worker_id]['status'] == 'connected':
            print(f"Closing session {session_id} on worker {worker_id}")
            if workers[worker_id].get('type') == 'internal':
                 local_worker.close_session(session_id)
            else:
                 workers[worker_id]['client'].emit('close_session', {'session_id': session_id})

if __name__ == '__main__':
    # --- INTERNAL WORKER SETUP ---
    
    def handle_internal_event(event_name, data):
        """Callback to bridge InternalWorker events to SocketIO."""
        data['worker_id'] = local_worker_id
        
        if event_name == 'term_output':
            # Use shared output handler (stores logs, broadcasts)
            on_worker_output(local_worker_id, data)
        else:
             # Pass other events directly (session_created, exec_result, etc.)
            socketio.emit(event_name, data)

    print("Initializing Internal Worker...")
    local_worker = InternalWorker(handle_internal_event)
    
    # Add to workers dict
    workers[local_worker_id] = {
        'type': 'internal',
        'status': 'connected',
        'url': 'internal',
        'name': 'Local Host Terminal',
        'sessions': {},
        'closed_sessions': set()
    }
    
    # Auto-start default session
    print("Starting default session-1...")
    local_worker.create_session('session-1')
    
    # Ensure Auth Config exists
    ConfigManager.load_config()
    
    start_tunnel()

    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        cleanup_worker()
        cleanup_tunnel()
