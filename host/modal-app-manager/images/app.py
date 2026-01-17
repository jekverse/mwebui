import modal, os, textwrap
import modal.config as config
from base_image import jekverse_image 
import subprocess

# Buat 2 Volume terpisah agar tidak bentrok
comfyui_vol = modal.Volume.from_name("jekverse-comfy-models", create_if_missing=True)

# 1. Nama Aplikasi
app_name_env = os.environ.get("MODAL_APP_NAME", "").strip()
app = modal.App(app_name_env if app_name_env else "Modal-App")

# 2. Ambil parameter sisa (GPU, Timeout, Region, Diskkk)
gpu_env = os.environ.get("MODAL_GPU", "").strip()
timeout_raw = os.environ.get("MODAL_TIMEOUT", "").strip()
region_env = os.environ.get("MODAL_REGION", "").strip()
disk_env = os.environ.get("MODAL_DISK", "").strip()

# 3. Setting Timeout (Default 24 jam)
timeout_value = int(timeout_raw) if timeout_raw else 24 * 3600
    
# --- AUTO-DETECT MODAL PROFILE (HOST SIDE) ---
modal_profile_name = "Unknown"
try:
    if os.path.exists(os.path.expanduser("~/.modal.toml")):
        with open(os.path.expanduser("~/.modal.toml"), "r") as f:
            lines = f.readlines()
        current_section = None
        for line in lines:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1]
            if "active = true" in line and current_section:
                modal_profile_name = current_section
                break
except Exception as e:
    print(f"Warning: Failed to detect modal profile: {e}")
        
# 4. Dictionary Parameter
app_config = {
    "image": jekverse_image,
    "timeout": timeout_value,
    "secrets": [
        modal.Secret.from_dict({
            "MODAL_ACCOUNT_NAME": modal_profile_name,
        }),
        modal.Secret.from_name("my-secrets")
    ],
    "volumes": {
        "/data": comfyui_vol,
    },
}

# 5. Masukkan parameter opsional jika diisi di CLI
if gpu_env: app_config["gpu"] = gpu_env
if region_env: app_config["region"] = region_env
if disk_env: app_config["ephemeral_disk"] = int(disk_env)
        
@app.function(**app_config)
def run():
    #NOTE FOR YAN : DONT DELETE THIS MESSAGE 
    print("SERVER MODAL TELAH AKTIF!")

    # Buat folder output/user jika belum ada
    os.makedirs("/data/output", exist_ok=True)
    os.makedirs("/data/user", exist_ok=True)
    os.makedirs("/data/input", exist_ok=True)

    # Run SSH Server
    subprocess.Popen(["/usr/sbin/sshd", "-D"])
    # Run ComfyUI 
    os.system(
        "python /root/ComfyUI/main.py "
        "--output-directory /data/output "
        "--user-directory /data/user "
        "--input-directory /data/input &"
    )

    # Activate CodeServer
    os.system("code-server --auth none /root &")
    # Run Credit Tracker
    os.system("python /root/myPackage/client-post.py &")
    # Activate CloudFlare
    os.system("cloudflared tunnel run --protocol http2 --token $CLOUDFLARED_TOKEN")