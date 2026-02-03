# Bug Fix: Duplicate Session Logs

## 🐛 **Problem**

Saat menjalankan satu session Modal VM, logs tercatat **2 kali**:
1. Entry pertama dengan status `"running"`
2. Entry kedua dengan status `"completed"`

Ini menyebabkan:
- ❌ Biaya di-charge 2x untuk session yang sama
- ❌ Balance berkurang lebih dari seharusnya
- ❌ UI menampilkan 2 entry untuk 1 session

### Screenshot Sebelum Fix:
```
Sessions: 2
Session #8388ff7 - Running  - $0.0410
Session #8388ff7 - Completed - $0.0576
Total: $0.0985 (seharusnya hanya $0.0576)
```

---

## 🔍 **Root Cause**

Di file `internal_worker.py` fungsi `sync_usage_from_volume()`:

**Workflow yang salah:**
1. **Sync pertama**: Session "8388ff74" berstatus `"running"` → Dicatat ke history
2. **Sync kedua**: Session "8388ff74" berubah status ke `"completed"` → Dicatat LAGI sebagai entry baru
3. **Result**: 2 entries untuk session yang sama!

**Kode lama (buggy):**
```python
# Line 324-345 (OLD)
if status == 'completed':
    if session_id in wallet['synced_sessions']:
        continue
    
    new_cost += cost  # ❌ Langsung tambah cost tanpa cek duplikat!
    new_sessions += 1
    
    wallet['history'].append({  # ❌ Append tanpa remove entry "running"
        'session_id': session_id,
        'status': 'completed'
    })
```

---

## ✅ **Solution**

### 1. Fix Kode di `internal_worker.py`

Tambahkan logika untuk **remove entry "running" lama** sebelum menambahkan entry "completed":

```python
# Line 324-350 (FIXED)
if status == 'completed':
    if session_id in wallet['synced_sessions']:
        continue
    
    # ✅ BUGFIX: Remove old "running" entry if exists
    running_idx = None
    for i, h in enumerate(wallet.get('history', [])):
        if h.get('session_id') == session_id and h.get('status') == 'running':
            running_idx = i
            break
    
    if running_idx is not None:
        # ✅ Remove running entry and only count cost difference
        old_cost = wallet['history'][running_idx].get('cost', 0)
        cost_diff = cost - old_cost
        new_cost += cost_diff if cost_diff > 0 else 0
        wallet['history'].pop(running_idx)  # ✅ Hapus entry running
    else:
        # No previous running entry, count full cost
        new_cost += cost
    
    # ✅ Add completed entry (hanya 1 kali)
    wallet['history'].append({
        'session_id': session_id,
        'status': 'completed'
    })
```

### 2. Cleanup Script untuk Data Lama

Created `fix_duplicate_sessions.py` untuk membersihkan duplikat yang sudah ada:

```bash
python3 fix_duplicate_sessions.py
```

**Hasil:**
```
✅ Fixed duplicates in wallet_sultanmahbebas38.json
   Original entries: 2
   Removed duplicates: 1
   Final entries: 1
   Balance: $79.901483 → $79.942446 (+$0.040963 refund)
```

---

## 📊 **Verifikasi**

### Sebelum Fix:
```json
{
    "balance": 79.901483,
    "history": [
        {
            "session_id": "8388ff74",
            "status": "running",
            "cost": 0.040963  // ❌ Duplikat
        },
        {
            "session_id": "8388ff74",
            "status": "completed",
            "cost": 0.057554  // ❌ Duplikat
        }
    ]
}
```

### Sesudah Fix:
```json
{
    "balance": 79.942446,  // ✅ +$0.040963 refund
    "history": [
        {
            "session_id": "8388ff74",
            "status": "completed",
            "cost": 0.057554  // ✅ Hanya 1 entry
        }
    ]
}
```

---

## 🎯 **Impact**

✅ **Fixed:**
- Session hanya tercatat 1x (completed atau running, tidak keduanya)
- Balance calculation sudah benar
- UI menampilkan jumlah session yang akurat

✅ **Refund:**
- Balance yang sudah di-charge 2x dikembalikan
- Script cleanup otomatis refund duplikat cost

---

## 🚀 **Testing**

Untuk test fix ini:

1. Jalankan Modal VM
2. Tunggu hingga selesai (completed)
3. Sync usage: klik "Wallet Logs" di UI
4. Verify: Hanya 1 entry untuk session tersebut

**Expected:**
- 1 session = 1 entry
- Cost = actual usage cost (tidak double)

---

## 📝 **Files Modified**

1. **`/host/internal_worker.py`** (line 324-350)
   - Fixed duplicate session logic
   
2. **`/host/fix_duplicate_sessions.py`** (NEW)
   - Script untuk cleanup duplikat existing

3. **`/host/modal-credit-tracker/wallet_*.json`**
   - Data cleaned up, balance refunded

---

**Date:** 2026-02-03  
**Status:** ✅ **FIXED & TESTED**
