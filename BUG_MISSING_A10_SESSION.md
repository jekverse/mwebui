# Bug Report: Session A10 Tidak Muncul di Wallet Logs

## 🐛 **Problem**

**Timeline:**
1. Start VM1 (L40S) ✅ - Tercatat
2. Start VM2 (H200) ✅ - Tercatat  
3. Stop VM1 (L40S) ✅ - Completed
4. Start VM3 (A10) ❌ - **TIDAK TERCATAT**

**Current State:**
- Dashboard: 2 VMs running (H200 + A10)
- Wallet Logs: Hanya H200 (A10 missing!)
- Volume data: Tidak ada session A10

---

## 🔍 **Root Cause Analysis**

### **Investigation Steps:**

1. **Checked Wallet File** (`wallet_sultanmahbebas38.json`):
   ```json
   {
     "sessions": [
       "8388ff74" - L40S (completed),
       "2e9a6031" - L40S (running → completed),
       "4fd79f2f" - H200 (running)
       // NO A10 SESSION!
     ]
   }
   ```

2. **Checked Volume Data** (`usage/sultanmahbebas38.json`):
   ```json
   {
     "sessions": [
       "8388ff74" - L40S,
       "2e9a6031" - L40S,
       "4fd79f2f" - H200
       // NO A10 SESSION!
     ]
   }
   ```

3. **Conclusion**: 
   - ❌ **A10 VM tidak menulis ke volume**
   - ✅ Sync mechanism berfungsi normal
   - ✅ L40S dan H200 tracking berjalan normal

---

## 🎯 **Possible Causes**

### **Cause #1: Wrong App Deployed** ⭐ (Most Likely)

VM A10 mungkin di-deploy dengan **app yang berbeda** yang tidak include `usage_tracker.py`.

**Check:**
```bash
# List all deployed apps
modal app list

# Check which app is running
modal app logs <app-name>
```

**Solution:**
- Pastikan deploy menggunakan app yang sama: `modal-app-manager/images/app.py`
- Verifikasi ada `from usage_tracker import start_tracking`

---

### **Cause #2: GPU Type Not Recognized**

GPU type mungkin tidak match dengan mapping.

**Current Mapping:**
```python
GPU_ALIASES = {
    "A10": "Nvidia A10",  # ✅ Sudah ada
    "H100": "Nvidia H100",
    "H200": "Nvidia H200",
    ...
}
```

**Check:**
```bash
# Cek GPU type yang digunakan
echo $MODAL_GPU  # Should be "A10" or "a10" or "nvidia-a10"
```

**Fix:**
Add more aliases if needed:
```python
GPU_ALIASES = {
    "A10": "Nvidia A10",
    "a10": "Nvidia A10",
    "nvidia-a10": "Nvidia A10",
    ...
}
```

---

### **Cause #3: Missing Environment Variable**

`MODAL_GPU_TYPE` atau `MODAL_ACCOUNT_NAME` tidak ter-set di VM A10.

**How variables are set:**
```python
# In app.py (host side)
app_config = {
    "secrets": [
        modal.Secret.from_dict({
            "MODAL_ACCOUNT_NAME": modal_profile_name,  # Auto-detected
            "MODAL_GPU_TYPE": gpu_env or "CPU",        # From CLI arg
        }),
    ],
}
```

**Check in VM:**
```python
# In VM, check env
import os
print("Account:", os.environ.get("MODAL_ACCOUNT_NAME"))
print("GPU:", os.environ.get("MODAL_GPU_TYPE"))
```

---

### **Cause #4: VM Crashed Before Tracker Started**

VM mungkin crash sebelum `start_tracking()` dipanggil atau sebelum first write (60 detik).

**Check logs:**
```bash
modal app logs <app-name> | grep "start_tracking"
modal app logs <app-name> | grep "UsageTracker"
```

---

## ✅ **Solutions & Debugging Steps**

### **Step 1: Verify Current Running Apps**

```bash
# List all running apps
modal app list

# Check logs of A10 VM
modal app logs Modal-App --from 10m
```

**Look for:**
- ✅ "🚀 SERVER MODAL TELAH AKTIF!"
- ✅ "UsageTracker initialized"
- ❌ Any errors during startup

---

### **Step 2: Add Debug Logging**

Update `app.py` to add more logging:

```python
@app.function(**app_config)
def run():
    from usage_tracker import start_tracking, stop_tracking
    
    print("🚀 SERVER MODAL TELAH AKTIF!")
    
    # Get account and GPU from environment
    account_name = os.environ.get("MODAL_ACCOUNT_NAME", "unknown")
    gpu_type = os.environ.get("MODAL_GPU_TYPE", "CPU")
    
    # DEBUG: Print environment
    print(f"DEBUG: Account = {account_name}")
    print(f"DEBUG: GPU Type = {gpu_type}")
    print(f"DEBUG: Starting usage tracker...")
    
    # Start usage tracking
    tracker = start_tracking(account_name, gpu_type, periodic=True)
    
    print(f"DEBUG: Tracker started with session_id = {tracker.session_id}")
    print(f"DEBUG: Usage file = {tracker.usage_file}")
    
    # ... rest of code
```

---

### **Step 3: Manual Verification**

SSH into VM A10 and check:

```bash
# Check if usage file exists
ls -la /data/usage/

# Check content
cat /data/usage/sultanmahbebas38.json

# Check if tracker is writing
watch -n 1 'cat /data/usage/sultanmahbebas38.json'
```

---

### **Step 4: Force Write on Start**

Update `usage_tracker.py` to write immediately on start:

```python
def start(self):
    """Start usage tracking."""
    self.start_time = time.time()
    print(f"UsageTracker: Started for {self.account_name}, GPU: {self.gpu_type}")
    print(f"UsageTracker: Session ID: {self.session_id}")
    print(f"UsageTracker: Writing to {self.usage_file}")
    
    # IMMEDIATE WRITE (don't wait 60 seconds)
    self._update_session(final=False)
    print(f"UsageTracker: Initial write completed")
```

---

## 🔧 **Quick Fix Implementation**

### **Option A: Add Immediate Write** ⭐ Recommended

```python
# In usage_tracker.py, modify start()
def start(self):
    """Start usage tracking."""
    self.start_time = time.time()
    self._update_session(final=False)  # Immediate write!
```

**Benefits:**
- Session appears immediately (not after 60s)
- Faster debugging
- Better UX

---

### **Option B: Reduce Update Interval**

```python
# In app.py
start_tracking(account_name, gpu_type, periodic=True)

# Change to 10 seconds for testing
_tracker_instance.start_periodic_updates(10)  # Was 60
```

---

## 📋 **Action Items**

### **Immediate:**
1. ✅ Fixed duplicate session bug in both `internal_worker.py` and `app.py`
2. ⏳ **Debug why A10 session not tracked**
3. ⏳ Add immediate write on tracker start
4. ⏳ Add debug logging

### **For User:**
Please check:
1. **App yang digunakan untuk start A10** - Apakah sama dengan H200/L40S?
2. **Modal logs** - Ada error saat start A10?
3. **GPU type** - Apa yang digunakan saat start A10?

### **Commands to Run:**

```bash
# 1. Check running apps
modal app list

# 2. Check A10 logs
modal app logs Modal-App --from 10m | grep -i "a10\|usage\|tracker"

# 3. Check volume
modal volume get jekverse-comfy-models usage/sultanmahbebas38.json /tmp/check.json
cat /tmp/check.json

# 4. Re-sync
# Use UI: Click "Wallet Logs" refresh button
```

---

## 💡 **Expected Behavior**

**Normal Flow:**
```
1. VM starts
2. start_tracking() called
3. Immediate write to /data/usage/{account}.json
4. Periodic updates every 60s
5. Final write on stop
6. Host syncs from volume
7. Session appears in wallet logs
```

**Current A10 Flow (Broken):**
```
1. VM starts
2. ??? (Something fails here)
3. No write to volume
4. No session recorded
```

---

**Next Steps:**
Silakan cek logs dan environment A10, lalu report hasilnya untuk debugging lebih lanjut.
