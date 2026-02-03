#!/usr/bin/env python3
"""
Cleanup Usage Tracker Logs
Clears usage history while preserving account and balance information.
"""

import os
import json
import argparse
from pathlib import Path

def cleanup_local_logs(tracker_dir: str = "modal-credit-tracker", reset_balance: bool = False):
    """
    Clean up local usage tracker logs.
    
    Args:
        tracker_dir: Directory containing wallet files
        reset_balance: If True, also reset balance to 80.0
    """
    tracker_path = Path(__file__).parent / tracker_dir
    
    if not tracker_path.exists():
        print(f"❌ Tracker directory not found: {tracker_path}")
        return
    
    wallet_files = list(tracker_path.glob("wallet_*.json"))
    
    if not wallet_files:
        print(f"✅ No wallet files found in {tracker_path}")
        return
    
    print(f"🧹 Cleaning up {len(wallet_files)} local wallet file(s)...\n")
    
    for wallet_file in wallet_files:
        try:
            with open(wallet_file, 'r') as f:
                data = json.load(f)
            
            account = data.get("account", "unknown")
            old_balance = data.get("balance", 0)
            old_history_count = len(data.get("history", []))
            old_synced_count = len(data.get("synced_sessions", []))
            
            # Clear history and synced sessions
            data["history"] = []
            data["synced_sessions"] = []
            
            # Optionally reset balance
            if reset_balance:
                data["balance"] = 80.0
            
            # Save cleaned data
            with open(wallet_file, 'w') as f:
                json.dump(data, f, indent=4)
            
            print(f"✅ {wallet_file.name}")
            print(f"   Account: {account}")
            print(f"   Balance: ${old_balance:.2f} → ${data['balance']:.2f}")
            print(f"   History: {old_history_count} entries → 0")
            print(f"   Synced: {old_synced_count} sessions → 0")
            print()
            
        except Exception as e:
            print(f"❌ Error processing {wallet_file.name}: {e}\n")

def cleanup_volume_logs(volume_name: str = "jekverse-comfy-models", account_name: str = None):
    """
    Clean up usage logs in Modal Volume.
    
    Args:
        volume_name: Name of the Modal volume
        account_name: Specific account to clean, or None for all
    """
    print(f"🧹 Cleaning up Modal Volume logs ({volume_name})...\n")
    
    # Generate Modal script to execute
    script_content = f'''
import modal
import json
import os

app = modal.App("cleanup-usage-logs")
volume = modal.Volume.from_name("{volume_name}")

@app.function(volumes={{"/data": volume}}, timeout=300)
def cleanup_usage_logs():
    """Remove usage log files from volume."""
    usage_dir = "/data/usage"
    
    if not os.path.exists(usage_dir):
        print("✅ No usage directory found in volume.")
        return
    
    files = os.listdir(usage_dir)
    
    if not files:
        print("✅ No usage files found.")
        return
    
    print(f"Found {{len(files)}} file(s) in /data/usage:")
    
    for filename in files:
        filepath = os.path.join(usage_dir, filename)
        
        try:
            # Read current data
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            account = data.get("account", "unknown")
            session_count = len(data.get("sessions", []))
            
            # Clear sessions
            data["sessions"] = []
            
            # Save cleaned data
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"✅ Cleaned {{filename}}")
            print(f"   Account: {{account}}")
            print(f"   Removed {{session_count}} session(s)")
            
        except Exception as e:
            print(f"❌ Error cleaning {{filename}}: {{e}}")
    
    # Commit changes to volume
    volume.commit()
    print("\\n✅ Volume committed successfully!")
'''
    
    # Save the cleanup script
    script_path = Path(__file__).parent / "cleanup_volume_script.py"
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    print(f"📝 Generated Modal cleanup script: {script_path}")
    print(f"\n🚀 To clean volume logs, run:")
    print(f"   modal run {script_path}::cleanup_usage_logs")
    print()

def main():
    parser = argparse.ArgumentParser(description="Cleanup usage tracker logs")
    parser.add_argument("--local", action="store_true", help="Clean local logs")
    parser.add_argument("--volume", action="store_true", help="Generate volume cleanup script")
    parser.add_argument("--reset-balance", action="store_true", help="Reset balance to 80.0")
    parser.add_argument("--volume-name", default="jekverse-comfy-models", help="Modal volume name")
    parser.add_argument("--all", action="store_true", help="Clean both local and generate volume script")
    
    args = parser.parse_args()
    
    # Default to --all if no options specified
    if not (args.local or args.volume or args.all):
        args.all = True
    
    if args.all or args.local:
        cleanup_local_logs(reset_balance=args.reset_balance)
    
    if args.all or args.volume:
        cleanup_volume_logs(volume_name=args.volume_name)
    
    print("=" * 60)
    print("✅ Cleanup process completed!")
    print("=" * 60)

if __name__ == "__main__":
    main()
