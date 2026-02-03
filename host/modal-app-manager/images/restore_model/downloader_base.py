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
def _prepare_directories():
    folders = [
        "checkpoints", "configs", "vae", "loras", "upscale_models", 
        "embeddings", "controlnet", "clip", "clip_vision", 
        "text_encoders", "diffusion_models", "unet", "audio_encoders"
    ]
    for folder in folders:
        os.makedirs(f"{MODELS_BASE_PATH}/{folder}", exist_ok=True)

def _download_file(url: str, dest_path: str, hf_token: str = None):
    """Download a single file using huggingface_hub or requests."""
    import requests
    from huggingface_hub import hf_hub_download
    
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    if "huggingface.co" in url:
        # Parse HuggingFace URL
        # Format: https://huggingface.co/{repo}/resolve/{branch}/{filename}
        parts = url.split("/")
        try:
            hf_idx = parts.index("huggingface.co")
            repo_id = f"{parts[hf_idx+1]}/{parts[hf_idx+2]}"
            # Find filename after 'resolve' or 'blob'
            if "resolve" in parts:
                filename = "/".join(parts[parts.index("resolve")+2:])
            elif "blob" in parts:
                filename = "/".join(parts[parts.index("blob")+2:])
            else:
                filename = parts[-1]
            
            print(f"  📥 HF download: {repo_id}/{filename}")
            downloaded = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=os.path.dirname(dest_path),
                token=hf_token
            )
            # Move to expected location if needed
            if downloaded != dest_path:
                import shutil
                shutil.move(downloaded, dest_path)
        except Exception as e:
            print(f"  ⚠️ HF download failed, using requests: {e}")
            _download_with_requests(url, dest_path, hf_token)
    else:
        _download_with_requests(url, dest_path, hf_token)

def _download_with_requests(url: str, dest_path: str, token: str = None):
    """Fallback download using requests."""
    import requests
    headers = {}
    if token and "huggingface.co" in url:
        headers["Authorization"] = f"Bearer {token}"
    
    print(f"  📥 Downloading: {url}")
    response = requests.get(url, headers=headers, stream=True)
    response.raise_for_status()
    
    with open(dest_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

# --- THE FACTORY FUNCTION ---
def create_downloader_app(app_name, download_list):
    """
    Factory function to create a downloader app.
    No external dependencies - uses huggingface_hub directly.
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
        account_name = os.environ.get("MODAL_ACCOUNT_NAME")
        hf_token = os.environ.get("HF_TOKEN")
        
        print(f"🚀 Running Downloader: {app_name}")
        print(f"👤 Modal account: {account_name}")
        
        _prepare_directories()
        
        print(f"⬇️ Downloading {len(download_list)} files...")
        
        success_count = 0
        for item in download_list:
            url = item.get("url")
            dest = item.get("dest") or item.get("path")
            
            if not url or not dest:
                print(f"  ⚠️ Skipping invalid item: {item}")
                continue
                
            # Ensure dest is full path
            if not dest.startswith("/"):
                dest = f"{MODELS_BASE_PATH}/{dest}"
            
            try:
                _download_file(url, dest, hf_token)
                print(f"  ✅ {os.path.basename(dest)}")
                success_count += 1
            except Exception as e:
                print(f"  ❌ Failed: {dest} - {e}")
        
        print(f"\n✨ Downloaded {success_count}/{len(download_list)} files")

    return app