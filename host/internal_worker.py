import eventlet
import os
import subprocess
import pty
import select
import struct
import fcntl
import termios
import json
import time
import shutil

# Enable eventlet patching if not already done
# eventlet.monkey_patch() 

class InternalWorker:
    def __init__(self, event_callback):
        """
        Args:
            event_callback: Function to call for emitting events back to the host.
                            Signature: (event_name, data_dict)
        """
        self.callback = event_callback
        self.sessions = {} # { session_id: { 'process': proc, 'master_fd': fd, 'cwd': cwd } }
        
        # --- Credit Tracker Config ---
        self.TRACKER_DIR = os.path.join(os.path.dirname(__file__), 'modal-credit-tracker')
        if not os.path.exists(self.TRACKER_DIR):
            os.makedirs(self.TRACKER_DIR)

    # --- TERMINAL SESSION MANAGEMENT ---

    def create_session(self, session_id):
        if session_id in self.sessions:
            return # Already exists
            
        try:
            # Create PTY
            master_fd, slave_fd = pty.openpty()
            
            # Set default window size
            try:
                # rows, cols, xpixels, ypixels
                winsize = struct.pack("HHHH", 30, 120, 0, 0)
                fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
            except Exception as e:
                print(f"Failed to set window size: {e}")
            
            def set_ctty():
                os.setsid()
                try:
                    fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
                except Exception as e:
                    print(f"Error setting ctty: {e}")

            # Start process (default shell)
            initial_cwd = os.path.expanduser('~')
            
            # Select Shell
            preferred_shells = [os.environ.get('SHELL'), '/bin/bash', '/bin/sh', '/bin/zsh']
            shell_cmd = '/bin/sh'
            for shell in preferred_shells:
                if shell and os.path.exists(shell) and os.access(shell, os.X_OK):
                    shell_cmd = shell
                    break
            
            print(f"InternalWorker: Starting session {session_id} with shell: {shell_cmd}")
            
            process = subprocess.Popen(
                [shell_cmd],
                cwd=initial_cwd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=set_ctty,
                close_fds=True
            )
            
            os.close(slave_fd)
            
            self.sessions[session_id] = {
                'process': process,
                'master_fd': master_fd,
                'cwd': initial_cwd,
                'history': '' 
            }
            
            # Start background reader
            eventlet.spawn(self._read_output_loop, master_fd, session_id)
            
            self.callback('session_created', {'session_id': session_id})
            
        except Exception as e:
            print(f"InternalWorker: Failed to create session: {e}")
            self.callback('output', {'output': f"Error creating session: {e}\n"})

    def _read_output_loop(self, fd, session_id):
        """Reads from PTY master fd."""
        # print(f"InternalWorker: Read loop started for {session_id}")
        while True:
            try:
                if session_id not in self.sessions:
                    break
                    
                # Eventlet-friendly select
                r, w, e = select.select([fd], [], [], 0.1)
                if fd in r:
                    data = os.read(fd, 1024)
                    if not data:
                        break
                    output_str = data.decode('utf-8', errors='replace')
                    
                    # Buffer history (Keep last 100KB)
                    if session_id in self.sessions:
                         self.sessions[session_id]['history'] += output_str
                         if len(self.sessions[session_id]['history']) > 100000:
                             self.sessions[session_id]['history'] = self.sessions[session_id]['history'][-100000:]
                             
                    self.callback('term_output', {'session_id': session_id, 'output': output_str})
                
                # Check process status
                session = self.sessions.get(session_id)
                if session and session['process'].poll() is not None:
                    break
            except OSError:
                break
            except Exception as e:
                print(f"InternalWorker: Read loop error {session_id}: {e}")
                break
        
        self.callback('term_output', {'session_id': session_id, 'output': '\n[Process exited]\n'})
        self.close_session(session_id)

    def get_history(self, session_id):
        if session_id in self.sessions:
            return self.sessions[session_id]['history']
        return ""

    def write_input(self, session_id, input_data):
        if session_id not in self.sessions:
            return
        
        fd = self.sessions[session_id]['master_fd']
        try:
            os.write(fd, input_data.encode('utf-8'))
        except Exception as e:
            print(f"InternalWorker: Write error {session_id}: {e}")

    def resize(self, session_id, cols, rows):
        if session_id in self.sessions:
            try:
                fd = self.sessions[session_id]['master_fd']
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
            except Exception as e:
                print(f"InternalWorker: Resize error {session_id}: {e}")

    def close_session(self, session_id):
        if session_id in self.sessions:
            session = self.sessions[session_id]
            
            # Close FD
            try:
                os.close(session['master_fd'])
            except:
                pass
            
            # Terminate Process
            proc = session['process']
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=1)
                except:
                    try:
                        proc.kill()
                    except:
                        pass
            
            del self.sessions[session_id]
            self.callback('session_closed', {'session_id': session_id})

    # --- EXEC COMMANDS ---

    def exec_command(self, command, cwd, request_id):
        try:
            cwd = os.path.expanduser(cwd if cwd else os.getcwd())
            
            result = subprocess.run(
                command, 
                shell=True, 
                cwd=cwd, 
                capture_output=True, 
                text=True,
                env={**os.environ, 'TERM': 'xterm'} 
            )
            
            self.callback('exec_result', {
                'id': request_id,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            })
        except Exception as e:
            self.callback('exec_result', {
                'id': request_id,
                'error': str(e),
                'returncode': -1
            })

    # --- WALLET / BALANCE ---

    def _get_account_file(self, account_name):
        return os.path.join(self.TRACKER_DIR, f"wallet_{account_name}.json")

    def _load_wallet_data(self, account_name):
        filename = self._get_account_file(account_name)
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return json.load(f)
        return {"account": account_name, "balance": 80.0, "last_signal_time": None, "history": []}
    
    def _save_wallet_data(self, account_name, data):
        with open(self._get_account_file(account_name), 'w') as f:
            json.dump(data, f, indent=4)

    def get_balance(self, account_name, request_id):
        if not account_name:
            return
            
        try:
            wallet_data = self._load_wallet_data(account_name)
            self.callback('exec_result', {
                'id': request_id,
                'stdout': json.dumps(wallet_data),
                'stderr': '',
                'returncode': 0
            })
        except Exception as e:
             self.callback('exec_result', {
                'id': request_id,
                'error': str(e),
                'returncode': 1
            })
    
    # --- SYNC USAGE FROM VOLUME (NEW SIMPLIFIED APPROACH) ---
    
    GPU_RATES = {
        "Nvidia B200": 6.75, "Nvidia H200": 5.04, "Nvidia H100": 4.45,
        "Nvidia A100, 80 GB": 3.00, "Nvidia A100, 40 GB": 2.60,
        "Nvidia L40S": 2.45, "Nvidia A10": 1.60, "Nvidia L4": 1.30, 
        "Nvidia T4": 1.09, "CPU": 0.1
    }
    
    def sync_usage_from_volume(self, account_name, volume_name, request_id):
        """
        Sync usage data from Modal Volume.
        
        This reads /data/usage/{account}.json from the volume and
        updates local wallet balance based on recorded sessions.
        """
        if not account_name or not volume_name:
            self.callback('exec_result', {
                'id': request_id,
                'stdout': '',
                'stderr': 'Account name and volume name required',
                'returncode': 1
            })
            return
            
        try:
            import tempfile
            
            # Use modal CLI to get the file from volume
            modal_bin = shutil.which('modal') or os.path.expanduser('~/.local/bin/modal')
            remote_path = f"usage/{account_name}.json"
            
            # Create temp file for the download
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
                tmp_path = tmp.name
            
            # Download usage file from volume
            # modal volume get <volume_name> <remote_path> <local_path>
            cmd = [modal_bin, 'volume', 'get', volume_name, remote_path, tmp_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                # File might not exist yet (no sessions recorded)
                self.callback('exec_result', {
                    'id': request_id,
                    'stdout': json.dumps({
                        'synced': False,
                        'message': 'No usage data found (VM may not have run yet)',
                        'details': result.stderr
                    }),
                    'stderr': '',
                    'returncode': 0
                })
                return
            
            # Parse usage data from volume
            with open(tmp_path, 'r') as f:
                usage_data = json.load(f)
            
            # Clean up temp file
            os.unlink(tmp_path)
            
            # Load existing wallet
            wallet = self._load_wallet_data(account_name)
            
            # Track which sessions we've already processed
            if 'synced_sessions' not in wallet:
                wallet['synced_sessions'] = []
            
            # Process each session from usage data
            new_cost = 0
            new_sessions = 0
            
            for session in usage_data.get('sessions', []):
                session_id = session.get('session_id')
                status = session.get('status', 'unknown')
                cost = session.get('cost', 0)
                
                # For completed sessions: only process if not already synced
                if status == 'completed':
                    if session_id in wallet['synced_sessions']:
                        continue
                    
                    # BUGFIX: Remove old "running" entry if exists to prevent duplicates
                    running_idx = None
                    for i, h in enumerate(wallet.get('history', [])):
                        if h.get('session_id') == session_id and h.get('status') == 'running':
                            running_idx = i
                            break
                    
                    if running_idx is not None:
                        # Remove running entry and only count the cost difference
                        old_cost = wallet['history'][running_idx].get('cost', 0)
                        cost_diff = cost - old_cost
                        new_cost += cost_diff if cost_diff > 0 else 0
                        # Remove the old running entry
                        wallet['history'].pop(running_idx)
                    else:
                        # No previous running entry, count full cost
                        new_cost += cost
                    
                    new_sessions += 1
                    
                    # Add completed entry to history
                    wallet['history'].append({
                        'session_id': session_id,
                        'gpu_type': session.get('gpu_type', 'Unknown'),
                        'start_time': session.get('start_time'),
                        'end_time': session.get('end_time'),
                        'duration_sec': session.get('duration_sec', 0),
                        'cost': cost,
                        'source': 'volume_sync',
                        'status': 'completed'
                    })
                    
                    # Mark as synced
                    wallet['synced_sessions'].append(session_id)
                    
                # For running sessions: update or create tracking entry
                elif status == 'running':
                    # Find existing running entry to update
                    existing_idx = None
                    for i, h in enumerate(wallet.get('history', [])):
                        if h.get('session_id') == session_id and h.get('status') == 'running':
                            existing_idx = i
                            break
                    
                    if existing_idx is not None:
                        # Update existing running entry
                        old_cost = wallet['history'][existing_idx].get('cost', 0)
                        cost_diff = cost - old_cost
                        if cost_diff > 0:
                            new_cost += cost_diff
                            wallet['history'][existing_idx].update({
                                'end_time': session.get('end_time'),
                                'duration_sec': session.get('duration_sec', 0),
                                'cost': cost
                            })
                    else:
                        # New running session
                        new_cost += cost
                        new_sessions += 1
                        wallet['history'].append({
                            'session_id': session_id,
                            'gpu_type': session.get('gpu_type', 'Unknown'),
                            'start_time': session.get('start_time'),
                            'end_time': session.get('end_time'),
                            'duration_sec': session.get('duration_sec', 0),
                            'cost': cost,
                            'source': 'volume_sync',
                            'status': 'running'
                        })
            
            # Deduct total cost from balance
            wallet['balance'] = max(0, wallet['balance'] - new_cost)
            
            # Save updated wallet
            self._save_wallet_data(account_name, wallet)
            
            self.callback('exec_result', {
                'id': request_id,
                'stdout': json.dumps({
                    'synced': True,
                    'new_sessions': new_sessions,
                    'cost_deducted': round(new_cost, 6),
                    'new_balance': round(wallet['balance'], 4)
                }),
                'stderr': '',
                'returncode': 0
            })
            
        except Exception as e:
            self.callback('exec_result', {
                'id': request_id,
                'stdout': '',
                'stderr': str(e),
                'returncode': 1
            })
            
    # --- HELPER FOR HEARTBEAT (CALLED FROM HOST ROUTE) ---
    
    def process_heartbeat_logic(self, account_name, gpu_type, gpu_rates, session_id=None):
        """
        Processes heartbeat logic independently per session_id to allow multiple VMs.
        """
        if gpu_type not in gpu_rates:
             return ({"detail": "Tipe GPU tidak terdaftar"}, 400)
             
        current_time = time.time()
        acc_data = self._load_wallet_data(account_name)
        
        # Initialize 'sessions' if not exists (migration)
        if "sessions" not in acc_data:
            acc_data["sessions"] = {}
            # Migrate legacy global last_signal_time to a default session if it exists and is recent
            if acc_data.get("last_signal_time"):
                 # Use a dummy session ID for legacy carryover or just ignore to start fresh
                 pass

        if acc_data["balance"] <= 0:
             return ({"status": "depleted", "message": "Saldo Habis! Ganti ke akun baru."}, 200)
             
        rate_per_hour = gpu_rates[gpu_type]
        rate_per_sec = rate_per_hour / 3600
        
        # Use session_id or 'default'
        sid = session_id or "default"
        
        last_signal = acc_data["sessions"].get(sid)
        
        if last_signal is not None:
            elapsed = current_time - last_signal
            if elapsed <= 60:
                cost = elapsed * rate_per_sec
                acc_data["balance"] = max(0, acc_data["balance"] - cost)
                
                # Update history (Session-aware)
                # We need to find the last entry *for this session* to update it, 
                # instead of just taking the last element of the list.
                target_entry = None
                
                # Search backwards for the last entry of this session
                if acc_data.get("history"):
                    for i in range(len(acc_data["history"]) - 1, -1, -1):
                        entry = acc_data["history"][i]
                        # Check matching session ID
                        # Legacy entries won't have session_id, so they get ignored (treated as finished)
                        if entry.get("session_id") == sid:
                            target_entry = entry
                            break
                            
                # If we found a recent entry (e.g. updated less than 5 mins ago), update it.
                # Otherwise, start a new entry.
                should_update = False
                if target_entry:
                     # Check if it's "active" (last update was recent)
                     # We don't store timestamp in entry, only "end_time" string.
                     # But we know we are calling this every ~20s.
                     # If the wallet file hasn't been touched in ages, we shouldn't update.
                     # Simpler check: If target_entry exists, we assume it's the current running session block.
                     # But if the user stopped and restarted the script, session_id changes, so we get a new entry anyway.
                     # If the network dropped for 1 hour, session_id is SAME.
                     # So we should check if 'total_duration' + 'start' roughly matches current time?
                     # Let's just update perfectly.
                     should_update = True

                if should_update and target_entry:
                    target_entry["end_time"] = time.strftime('%H:%M:%S')
                    target_entry["total_duration_sec"] = round(target_entry.get("total_duration_sec", 0) + elapsed, 2)
                    target_entry["total_cost"] = round(target_entry.get("total_cost", 0) + cost, 6)
                    target_entry["final_balance"] = round(acc_data["balance"], 4)
                else:
                    # Append new entry
                    acc_data["history"].append({
                        "session_id": sid, # Track ownership
                        "start_time": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "end_time": time.strftime('%H:%M:%S'),
                        "gpu_type": gpu_type,
                        "total_duration_sec": round(elapsed, 2),
                        "total_cost": round(cost, 6),
                        "final_balance": round(acc_data["balance"], 4)
                    })
            else:
                # New session after timeout -> No deduction, just reset timer
                pass
        
        # Update session timestamp
        acc_data["sessions"][sid] = current_time
        
        # Cleanup old sessions (optional, e.g. > 1 hour inactive)
        active_sessions = {}
        for s, t in acc_data["sessions"].items():
            if current_time - t < 3600: # Keep 1 hour history of sessions
                active_sessions[s] = t
        acc_data["sessions"] = active_sessions

        self._save_wallet_data(account_name, acc_data)
        
        rem_hours = acc_data["balance"] / rate_per_hour if rate_per_hour > 0 else 0
        time_left = f"{int(rem_hours)}j {int((rem_hours % 1) * 60)}m"
        
        return ({
            "account": account_name,
            "remaining": f"${round(acc_data['balance'], 4)}",
            "estimate": time_left,
            "status": "active"
        }, 200)
