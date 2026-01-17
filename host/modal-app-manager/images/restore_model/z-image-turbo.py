# filename: download_z_image.py
from downloader_base import create_downloader_app, MODELS_BASE_PATH

# Daftar URL untuk ComfyUI Z-Images
Z_IMAGE_DOWNLOADS = [
    {
        "url": "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors",
        "directory": f"{MODELS_BASE_PATH}/text_encoders"
    },
    {
        "url": "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors",
        "directory": f"{MODELS_BASE_PATH}/vae"
    },
    {
        "url": "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors",
        "directory": f"{MODELS_BASE_PATH}/diffusion_models"
    },
    {
        "url": "https://huggingface.co/tarn59/pixel_art_style_lora_z_image_turbo/resolve/main/pixel_art_style_z_image_turbo.safetensors",
        "directory": f"{MODELS_BASE_PATH}/loras"
    }
]

# Membuat App Modal menggunakan Factory dari downloader_base
app = create_downloader_app("Downloader-Z-Image", Z_IMAGE_DOWNLOADS)