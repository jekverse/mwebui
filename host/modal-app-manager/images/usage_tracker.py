"""
Usage Tracker - Embedded Credit Tracking for Modal VMs

This module writes usage data directly to the Modal Volume,
eliminating the need for external dependencies, Cloudflare tunnels,
and real-time heartbeat connections.

Usage:
    tracker = UsageTracker(account_name="jekverse-main", gpu_type="A10")
    tracker.start()
    # ... VM runs ...
    tracker.stop()  # Call on shutdown or periodically
"""

import os
import json
import time
import uuid
import atexit
import threading
from datetime import datetime, timezone, timedelta

# Define Jakarta timezone (UTC+7)
JAKARTA_TZ = timezone(timedelta(hours=7))

# GPU Rates ($/hour) - Same as host/app.py
GPU_RATES = {
    "Nvidia B200": 6.75,
    "Nvidia H200": 5.04,
    "Nvidia H100": 4.45,
    "Nvidia A100, 80 GB": 3.00,
    "Nvidia A100, 40 GB": 2.60,
    "Nvidia L40S": 2.45,
    "Nvidia A10": 1.60,
    "Nvidia L4": 1.30,
    "Nvidia T4": 1.09,
    "CPU": 0.1
}

# Aliases for easier use
GPU_ALIASES = {
    "A10": "Nvidia A10",
    "A100": "Nvidia A100, 80 GB",
    "A100-40": "Nvidia A100, 40 GB",
    "H100": "Nvidia H100",
    "H200": "Nvidia H200",
    "T4": "Nvidia T4",
    "L4": "Nvidia L4",
    "L40S": "Nvidia L40S",
}

USAGE_DIR = "/data/usage"


class UsageTracker:
    """
    Simple usage tracker that writes to Modal Volume.
    No network connection required.
    """
    
    def __init__(self, account_name: str, gpu_type: str = "CPU"):
        self.account_name = account_name
        self.gpu_type = GPU_ALIASES.get(gpu_type, gpu_type)
        self.session_id = str(uuid.uuid4())[:8]
        self.start_time = None
        self.usage_file = os.path.join(USAGE_DIR, f"{account_name}.json")
        self._running = False
        self._update_thread = None
        
    def _ensure_dir(self):
        try:
            os.makedirs(USAGE_DIR, exist_ok=True)
            print(f"✅ Usage directory ensured: {USAGE_DIR}")
        except Exception as e:
            print(f"❌ ERROR creating usage directory {USAGE_DIR}: {e}")
            raise
        
    def _load_usage_data(self) -> dict:
        """Load existing usage data or create new."""
        if os.path.exists(self.usage_file):
            try:
                with open(self.usage_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "account": self.account_name,
            "sessions": []
        }
    
    def _save_usage_data(self, data: dict):
        """Save usage data to volume."""
        try:
            self._ensure_dir()
            print(f"📝 Writing to {self.usage_file}...")
            with open(self.usage_file, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"✅ Successfully wrote {len(data.get('sessions', []))} session(s)")
        except Exception as e:
            print(f"❌ ERROR saving usage data to {self.usage_file}: {e}")
            print(f"   Error type: {type(e).__name__}")
            print(f"   Data: {data}")
            raise
            
    def _get_rate(self) -> float:
        """Get hourly rate for current GPU type."""
        return GPU_RATES.get(self.gpu_type, 0.1)
    
    def _calculate_cost(self, duration_sec: float) -> float:
        """Calculate cost based on duration."""
        hours = duration_sec / 3600
        return round(hours * self._get_rate(), 6)
    
    def start(self):
        """Start tracking usage."""
        self.start_time = time.time()
        self._running = True
        self._ensure_dir()
        
        # Register atexit handler to save on shutdown
        atexit.register(self.stop)
        
        # Create initial session entry
        self._update_session()
        
        print(f"📊 Usage Tracker Started")
        print(f"   Account: {self.account_name}")
        print(f"   GPU: {self.gpu_type} (${self._get_rate()}/hr)")
        print(f"   Session: {self.session_id}")
        
    def stop(self):
        """Stop tracking and save final usage."""
        if not self._running:
            return
            
        self._running = False
        self._update_session(final=True)
        
        duration = time.time() - self.start_time
        cost = self._calculate_cost(duration)
        print(f"📊 Usage Tracker Stopped")
        print(f"   Duration: {duration:.0f}s")
        print(f"   Cost: ${cost:.4f}")
        
    def _update_session(self, final: bool = False):
        """Update current session in usage file."""
        if not self.start_time:
            return
        
        try:
            now = time.time()
            duration_sec = now - self.start_time
            
            print(f"🔄 Updating session {self.session_id[:8]}... (final={final})")
            
            data = self._load_usage_data()
            
            # Find existing session or create new
            session_entry = None
            for s in data["sessions"]:
                if s.get("session_id") == self.session_id:
                    session_entry = s
                    break
                    
            if session_entry is None:
                print(f"  Creating new session entry for {self.session_id[:8]}")
                session_entry = {
                    "session_id": self.session_id,
                    "gpu_type": self.gpu_type,
                    "start_time": datetime.fromtimestamp(self.start_time, tz=JAKARTA_TZ).isoformat(),
                }
                data["sessions"].append(session_entry)
            else:
                print(f"  Updating existing session entry")
            
            # Update session
            session_entry["end_time"] = datetime.fromtimestamp(now, tz=JAKARTA_TZ).isoformat()
            session_entry["duration_sec"] = round(duration_sec, 2)
            session_entry["cost"] = self._calculate_cost(duration_sec)
            session_entry["status"] = "completed" if final else "running"
            
            print(f"  Duration: {duration_sec:.0f}s, Cost: ${session_entry['cost']:.4f}")
            
            self._save_usage_data(data)
        except Exception as e:
            print(f"❌ ERROR in _update_session: {e}")
            print(f"   Session ID: {self.session_id}")
            print(f"   GPU Type: {self.gpu_type}")
            print(f"   Usage file: {self.usage_file}")
            # Don't raise - allow VM to continue running
            import traceback
            traceback.print_exc()
        
    def start_periodic_updates(self, interval_sec: int = 60):
        """Start background thread for periodic updates."""
        def _update_loop():
            while self._running:
                time.sleep(interval_sec)
                if self._running:
                    self._update_session()
                    
        self._update_thread = threading.Thread(target=_update_loop, daemon=True)
        self._update_thread.start()


# Convenience function for quick usage
_tracker_instance = None

def start_tracking(account_name: str, gpu_type: str = "CPU", periodic: bool = True):
    """
    Start usage tracking (singleton pattern).
    
    Args:
        account_name: Modal account/profile name
        gpu_type: GPU type (e.g., "A10", "H100", "T4")
        periodic: Enable periodic updates (default: 60s)
    """
    global _tracker_instance
    _tracker_instance = UsageTracker(account_name, gpu_type)
    _tracker_instance.start()
    if periodic:
        _tracker_instance.start_periodic_updates(60)
    return _tracker_instance

def stop_tracking():
    """Stop usage tracking."""
    global _tracker_instance
    if _tracker_instance:
        _tracker_instance.stop()
        _tracker_instance = None
