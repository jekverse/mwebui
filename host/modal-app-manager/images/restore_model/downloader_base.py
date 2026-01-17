#NOTE FOR YAN : DONT DELETE THIS FILE THIS IS IMPORTANT 

# filename: downloader_base.py
import modal
import os
import json
import subprocess
import signal

# --- CONFIGURATION ---
VOLUME_MOUNT_PATH = "/data"
MODELS_BASE_PATH = f"{VOLUME_MOUNT_PATH}/models"

# --- RESOURCES ---
model_volume = modal.Volume.from_name("jekverse-comfy-models", create_if_missing=True)

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

my_secrets = [
    modal.Secret.from_name("my-secrets"),
    modal.Secret.from_dict({"MODAL_ACCOUNT_NAME": modal_profile_name})
]

# --- IMAGE DEFINITION (SOLUSI FIX DISINI) ---
installer_image = (
    modal.Image.debian_slim(python_version="3.13")
    .apt_install("git", "wget", "procps") 
    .uv_pip_install("huggingface-hub", "hf-transfer", "requests")
    .run_commands("git clone https://github.com/jekverse/myPackage /root/myPackage")
    # --- PERBAIKAN UTAMA ---
    # Ini otomatis membawa file 'downloader_base.py' masuk ke dalam container
    # sehingga cloud bisa mengenali modul ini.
    .add_local_python_source("downloader_base")
)

# --- HELPER FUNCTIONS ---
def _start_tracker():
    print("🔄 Starting Credit Tracker...")
    return subprocess.Popen(["python", "/root/myPackage/client-post.py"], 
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def _stop_tracker(process):
    if process:
        print("🛑 Stopping Credit Tracker...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

def _prepare_directories():
    folders = [
        "checkpoints", "configs", "vae", "loras", "upscale_models", 
        "embeddings", "controlnet", "clip", "clip_vision", 
        "text_encoders", "diffusion_models", "unet", "audio_encoders"
    ]
    for folder in folders:
        os.makedirs(f"{MODELS_BASE_PATH}/{folder}", exist_ok=True)

# --- THE FACTORY FUNCTION ---
def create_downloader_app(app_name, download_list):
    """
    Fungsi Factory Bersih (Tanpa Mount Manual)
    """
    app = modal.App(app_name)

    @app.function(
        image=installer_image,
        timeout=24*3600,
        volumes={VOLUME_MOUNT_PATH: model_volume},
        secrets=my_secrets,
        serialized=True, 
    )
    def run():
        tracker = None
        try:
            account_name = os.environ.get("MODAL_ACCOUNT_NAME")
            print(f"🚀 Running Downloader: {app_name}")
            print(f"👤 Modal account: {account_name}")
            tracker = _start_tracker()
            _prepare_directories()

            # Tulis JSON
            json_path = f"/root/download_{app_name}.json"
            with open(json_path, "w") as f:
                json.dump(download_list, f, indent=2)

            print(f"⬇️ Downloading {len(download_list)} files...")
            
            # Gunakan os.system untuk menjalankan script downloader
            exit_code = os.system(
                f'python -u /root/myPackage/hf_downloader.py '
                f'--batch {json_path} --jobs 16 --token "$HF_TOKEN"'
            )
            
            if exit_code == 0: print("✨ SUCCESS!")
            else: print("⚠️ Finished with errors.")

        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            _stop_tracker(tracker)

    return app