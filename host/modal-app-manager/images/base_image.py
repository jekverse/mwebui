import modal
import os
import sys
import json
import textwrap

# --- 1. CONFIGURATION & CONSTANTS ---
VOLUME_MOUNT_PATH = "/data"
MODELS_BASE_PATH = f"{VOLUME_MOUNT_PATH}/models"
app = modal.App("Updating-Image")
modal_secret = modal.Secret.from_name("my-secrets")

# Define Volume (Auto Create)
model_volume = modal.Volume.from_name("jekverse-comfy-models", create_if_missing=True)

def install_comfyui():
    # Clone ComfyUI
    print("Cloning ComfyUI...")
    os.system("git clone https://github.com/comfyanonymous/ComfyUI")
    
    # Clone ComfyUI Manager  
    print("Installing ComfyUI Manager...") 
    os.system("cd /root/ComfyUI/custom_nodes && git clone https://github.com/Comfy-Org/ComfyUI-Manager")

    # Install ComfyUI Deps
    print("Installing dependencies ComfyUI...")
    os.system("uv pip install --system -r /root/ComfyUI/requirements.txt")
    
    # Install ComfyUI Manager Deps
    print("Installing dependencies ComfyUI Manager...")
    os.system("uv pip install --system -r /root/ComfyUI/custom_nodes/ComfyUI-Manager/requirements.txt")
    
    # Clone Custom Nodes { parallel method }
    print("Cloning Custom_nodes")
    os.system(textwrap.dedent("""
        cd /root/ComfyUI/custom_nodes && \
        cat <<'EOF' | parallel -j32 "git clone --depth=1 {} || true"
        https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
        https://github.com/jekverse/terminal-comfyui.git
        https://github.com/jekverse/comfyui-downloader.git
        EOF
    """))
    os.system("python /root/ComfyUI/custom_nodes/ComfyUI-Manager/cm-cli.py restore-dependencies")

def create_comfy_config():
    print("📝 Creating extra_model_paths.yaml...")
    
    config_content = textwrap.dedent(f"""
        comfyui:
            base_path: {MODELS_BASE_PATH}
            
            # Checkpoints standar (SD1.5/SDXL)
            checkpoints: checkpoints
            
            # Text Encoders (T5, Qwen, CLIP)
            # Kita arahkan agar membaca folder 'text_encoders' DAN 'clip'
            text_encoders: |
                text_encoders
                clip
            
            # Diffusion Models (Wan2.1, Flux, UNET)
            # Kita arahkan agar membaca 'diffusion_models' DAN 'unet'
            diffusion_models: |
                diffusion_models
                unet
            
            # Komponen lainnya
            vae: vae
            loras: loras
            upscale_models: upscale_models
            embeddings: embeddings
            controlnet: controlnet
            clip_vision: clip_vision
            configs: configs
            
            # Support untuk Audio (jika pakai node audio)
            audio_encoders: audio_encoders
    """).strip()

    # Tulis file ke folder ComfyUI
    with open("/root/ComfyUI/extra_model_paths.yaml", "w") as f:
        f.write(config_content)
    
    print("✅ Configuration file created:")
    print(config_content) # Print untuk memastikan formatnya benar di logs

def install_dev_tools():
    """Install development tools (code-server, gh cli, etc.)"""
    # Install Code Server
    print("Installing Code Server...")
    os.system('''
    curl -fsSL https://code-server.dev/install.sh | sh && \
    mkdir -p /root/.local/share/code-server/User && \
    echo '{"workbench.colorTheme": "Default Dark+"}' > /root/.local/share/code-server/User/settings.json
    ''')
    
    # Install GitHub CLI 
    os.system("curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg")
    os.system("chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg")
    os.system("echo \"deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null")
    os.system("apt update && apt install gh -y")
    
    # Set essential tokens in bashrc
    os.system("echo \"export GH_TOKEN=$GH_TOKEN\" >> ~/.bashrc")
    os.system("echo \"export HF_TOKEN=$HF_TOKEN\" >> ~/.bashrc")
    
    # Login GitHub
    os.system("echo $GH_TOKEN | gh auth login --with-token")
    os.system("gh auth setup-git")
    os.system("git config --global user.email \"sultanmahbebas38@gmail.com\"")
    os.system("git config --global user.name \"jekverse\"")
    
    # Install Git LFS
    os.system("apt install git-lfs -y")
    os.system("git lfs install")
    
    print("✅ Dev tools installed successfully!")

# Definisi Image dipindahkan ke sini
jekverse_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "wget", "curl", "aria2", "lsof", "libgl1", "libglib2.0-0", "parallel", "openssh-server", "procps", "ca-certificates", "neovim", "ffmpeg")
    .uv_pip_install("huggingface-hub", "hf-transfer", "requests")
    
    .run_function(install_comfyui, secrets=[modal_secret])
    .run_function(create_comfy_config) 
    .run_function(install_dev_tools, secrets=[modal_secret])
    
    # Add embedded usage tracker LAST (Modal requirement)
    .add_local_python_source("usage_tracker")
)

# Gunakan image yang sudah di-import
@app.function(image=jekverse_image, timeout=24*3600,volumes={VOLUME_MOUNT_PATH: model_volume}, secrets=[modal_secret])
def run():
    print("Image updated successfully!")