# filename: download_flux.py
from downloader_base import create_downloader_app, MODELS_BASE_PATH

FLUX_DOWNLOADS = [
    {
        "url": "https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors",
        "directory": f"{MODELS_BASE_PATH}/vae"
    },
    {
        "url": "https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/text_encoders/mistral_3_small_flux2_bf16.safetensors",
        "directory": f"{MODELS_BASE_PATH}/text_encoders"
    },
    {
        "url": "https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/diffusion_models/flux2_dev_fp8mixed.safetensors",
        "directory": f"{MODELS_BASE_PATH}/diffusion_models"
    },
    {
        "url": "https://huggingface.co/ostris/flux2_berthe_morisot/resolve/main/flux2_berthe_morisot.safetensors",
        "directory": f"{MODELS_BASE_PATH}/loras"
    }
]

# Perhatikan nama App-nya beda agar mudah dipantau di dashboard
app = create_downloader_app("Downloader-Flux", FLUX_DOWNLOADS)