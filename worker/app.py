import eventlet
eventlet.monkey_patch()

import os
import subprocess
import pty
import select
import signal
import time
import struct
import fcntl
import termios
from flask import Flask
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret!')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Global state
sessions = {} # { session_id: { 'process': proc, 'master_fd': fd, 'cwd': cwd } }

@socketio.on('connect')
def handle_connect(auth):
    print(f"Client connected with auth: {auth}")
    # Use default token if not set in .env
    token = os.getenv('WORKER_AUTH_TOKEN', 'default-secret-key')
    
    if auth.get('token') != token:
        print("Authentication failed: Invalid token")
        return False # Reject connection

    print("Authentication successful")
    emit('output', {'output': f'Connected to Worker Node (Multi-Tab Enabled)\n'})
    
    # Auto-create default session 'session-1' if it doesn't exist
    if 'session-1' not in sessions:
        print("Initializing default session-1")
        create_session_internal('session-1')

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")

def close_session_internal(session_id):
    if session_id in sessions:
        session = sessions[session_id]
        print(f"Closing session {session_id}")
        
        # Close FD
        if session['master_fd']:
            try:
                os.close(session['master_fd'])
            except:
                pass
        
        # Kill process
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
        
        del sessions[session_id]
        socketio.emit('session_closed', {'session_id': session_id})

def read_output_loop(fd, session_id):
    """Reads from the PTY master file descriptor and emits to socket."""
    print(f"Starting read loop for Session: {session_id} (FD: {fd})")
    while True:
        try:
            # Check if session still exists
            if session_id not in sessions:
                break
                
            # Wait for data to be available
            r, w, e = select.select([fd], [], [], 0.1)
            if fd in r:
                data = os.read(fd, 1024)
                if not data:
                    break
                # Decode bytes to string
                output_str = data.decode('utf-8', errors='replace')
                socketio.emit('term_output', {'session_id': session_id, 'output': output_str})
            
            # Check if process is still alive
            session = sessions.get(session_id)
            if session and session['process'].poll() is not None:
                break
        except OSError:
            break
        except Exception as e:
            print(f"Read loop error for {session_id}: {e}")
            break
    
    print(f"Read loop finished for {session_id}")
    socketio.emit('term_output', {'session_id': session_id, 'output': '\n[Process exited]\n'})
    # Cleanup session if process exited
    if session_id in sessions:
        close_session_internal(session_id)

def create_session_internal(session_id):
    if session_id in sessions:
        return # Already exists
        
    try:
        # Create PTY
        master_fd, slave_fd = pty.openpty()
        
        # Set default window size (cols=120, rows=30) to prevent table wrapping
        try:
            import struct
            import fcntl
            import termios
            # struct winsize { unsigned short ws_row; unsigned short ws_col; ... }
            # rows, cols, xpixels, ypixels
            winsize = struct.pack("HHHH", 30, 120, 0, 0)
            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
        except Exception as e:
            print(f"Failed to set window size: {e}")
        
        def set_ctty():
            os.setsid()
            try:
                import fcntl
                import termios
                fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
            except Exception as e:
                print(f"Error setting ctty: {e}")

        # Start process (default shell)
        # Use home directory as initial CWD
        initial_cwd = os.path.expanduser('~')
        
        # Determine shell to use (Fallback to /bin/sh if bash is missing)
        preferred_shells = [os.environ.get('SHELL'), '/bin/bash', '/bin/sh', '/bin/zsh']
        shell_cmd = '/bin/sh' # Ultimate fallback
        
        for shell in preferred_shells:
            if shell and os.path.exists(shell) and os.access(shell, os.X_OK):
                shell_cmd = shell
                break
        
        print(f"Starting session {session_id} with shell: {shell_cmd}")
        
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
        
        sessions[session_id] = {
            'process': process,
            'master_fd': master_fd,
            'cwd': initial_cwd
        }
        
        socketio.start_background_task(target=read_output_loop, fd=master_fd, session_id=session_id)
        socketio.emit('session_created', {'session_id': session_id})
        
    except Exception as e:
        print(f"Failed to create session: {e}")
        socketio.emit('output', {'output': f"Error creating session: {e}\n"})

@socketio.on('create_session')
def handle_create_session(data):
    session_id = data.get('session_id')
    print(f"Creating session: {session_id}")
    create_session_internal(session_id)

@socketio.on('close_session')
def handle_close_session(data):
    session_id = data.get('session_id')
    close_session_internal(session_id)

@socketio.on('command')
def handle_command(data):
    session_id = data.get('session_id')
    cmd = data.get('cmd')
    
    if not session_id or session_id not in sessions:
        print(f"Invalid session: {session_id}")
        return

    session = sessions[session_id]
    master_fd = session['master_fd']
    
    # In PTY mode, we just write input to the master FD
    # The running shell (bash) will handle execution
    try:
        if cmd:
            input_data = cmd + '\n'
            os.write(master_fd, input_data.encode('utf-8'))
    except Exception as e:
        print(f"Error writing to session {session_id}: {e}")

@socketio.on('term_input')
def handle_term_input(data):
    session_id = data.get('session_id')
    input_data = data.get('input')
    
    if not session_id or session_id not in sessions:
        return

    session = sessions[session_id]
    master_fd = session['master_fd']
    
    try:
        if input_data:
            os.write(master_fd, input_data.encode('utf-8'))
    except Exception as e:
        print(f"Error writing to session {session_id}: {e}")

@socketio.on('resize')
def handle_resize(data):
    session_id = data.get('session_id')
    cols = data.get('cols')
    rows = data.get('rows')
    
    if session_id in sessions:
        try:
            master_fd = sessions[session_id]['master_fd']
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
        except Exception as e:
            print(f"Error resizing session {session_id}: {e}")

@socketio.on('send_signal')
def handle_signal(data):
    session_id = data.get('session_id')
    sig_type = data.get('signal', 'SIGINT')
    
    if session_id in sessions:
        session = sessions[session_id]
        proc = session['process']
        if proc.poll() is None:
            try:
                if sig_type == 'SIGINT':
                    # Send ASCII ETX (Ctrl+C) to PTY master
                    # This simulates a physical keypress and allows the shell/process to handle it naturally
                    os.write(session['master_fd'], b'\x03')
                elif sig_type == 'SIGKILL':
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception as e:
                print(f"Error sending signal: {e}")

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5001, debug=True, allow_unsafe_werkzeug=True)
