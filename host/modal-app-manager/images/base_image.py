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

def setup_ssh():
    # 1. Setup Folder
    print("Setting up SSH...")
    os.system("mkdir -p /run/sshd")
    os.system("mkdir -p /root/.ssh")
    print("Folder is created")
    # 2. AMBIL KEY DARI ENV (Python Way)
    ssh_key = os.environ.get("SSH_KEY")

    # DEBUGGING
    if not ssh_key:
        print("❌ FATAL: Variable SSH_KEY kosong atau tidak ditemukan!")
        sys.exit(1)
    else:
        print(f"✅ SSH_KEY ditemukan (Panjang: {len(ssh_key)} karakter)")
        print(f"   Awal Key: {ssh_key[:20]}...")

    # 3. TULIS KE FILE (Python Way)
    with open("/root/.ssh/authorized_keys", "w") as f:
        f.write(ssh_key.strip() + "\n")

    # 4. Permission & Config (Sama seperti yang berhasil)
    os.system("chmod 700 /root/.ssh")
    os.system("chmod 600 /root/.ssh/authorized_keys")

    # Config SSHD
    os.system("sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config")
    os.system("sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config")
    
    print("🚀 SSH Setup Selesai.")

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

def install_myPackage():
    # Install Code Server
    print("Installing Code Server...")
    os.system('''
    curl -fsSL https://code-server.dev/install.sh | sh && \
    mkdir -p /root/.local/share/code-server/User && \
    echo '{"workbench.colorTheme": "Default Dark+"}' > /root/.local/share/code-server/User/settings.json
    ''')
    # Install CloudFlare
    os.system("wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared && chmod +x cloudflared && mv cloudflared /usr/local/bin/")
    # Install GitHub CLI 
    os.system("curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg")
    os.system("chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg")
    os.system("echo \"deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null")
    os.system("apt update && apt install gh -y")
    # Set Token 
    os.system("echo \"export GH_TOKEN=$GH_TOKEN\" >> ~/.bashrc")
    os.system("echo \"export HF_TOKEN=$HF_TOKEN\" >> ~/.bashrc")
    os.system("echo \"export CLOUDFLARED_TOKEN=$CLOUDFLARED_TOKEN\" >> ~/.bashrc")
    os.system("echo \"export CF_CLIENT_ID=$CF_CLIENT_ID\" >> ~/.bashrc")
    os.system("echo \"export CF_CLIENT_SECRET=$CF_CLIENT_SECRET\" >> ~/.bashrc")
    os.system("echo \"export API_URL=$API_URL\" >> ~/.bashrc")
    os.system("echo \"export API_KEY=$API_KEY\" >> ~/.bashrc")
    # Login GitHub
    os.system("echo $GH_TOKEN | gh auth login --with-token")
    os.system("gh auth setup-git")
    os.system("git config --global user.email \"sultanmahbebas38@gmail.com\"")
    os.system("git config --global user.name \"jekverse\"")
    # Install Git LFS
    os.system("apt install git-lfs -y")
    os.system("git lfs install")
    # Install myPackage
    #NOTE FOR YAN : DONT DELETE THIS REPO ITS FOR DOWNLOADING WITH HF & CREDIT TRACKER
    print("Installing myPackage...")
    os.system("git clone https://github.com/jekverse/myPackage")
    print("myPackage installed successfully!")

# Definisi Image dipindahkan ke sini
jekverse_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "wget", "curl", "aria2", "lsof", "libgl1", "libglib2.0-0", "parallel", "openssh-server", "procps", "ca-certificates", "neovim","ffmpeg")
    .uv_pip_install("huggingface-hub", "hf-transfer", "requests")

    .run_function(install_comfyui, secrets=[modal_secret])
    .run_function(create_comfy_config) 
    .run_function(setup_ssh, secrets=[modal_secret])
    .run_function(install_myPackage, secrets=[modal_secret])
)

# Gunakan image yang sudah di-import
@app.function(image=jekverse_image, timeout=24*3600,volumes={VOLUME_MOUNT_PATH: model_volume}, secrets=[modal_secret])
def run():
    print("Image updated successfully!")