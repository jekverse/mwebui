# filename: download_noobai.py
from downloader_base import create_downloader_app, MODELS_BASE_PATH

NOOBAI_DOWNLOADS = [
    {
        "url": "https://huggingface.co/Comfy-Org/NewBie-image-Exp0.1_repackaged/resolve/main/split_files/diffusion_models/NewBie-Image-Exp0.1-bf16.safetensors",
        "directory": f"{MODELS_BASE_PATH}/diffusion_models"
    },
    {
        "url": "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors",
        "directory": f"{MODELS_BASE_PATH}/vae"
    },
    {
        "url": "https://huggingface.co/Comfy-Org/NewBie-image-Exp0.1_repackaged/resolve/main/split_files/text_encoders/gemma_3_4b_it_bf16.safetensors",
        "directory": f"{MODELS_BASE_PATH}/text_encoders"
    },
    {
        "url": "https://huggingface.co/Comfy-Org/NewBie-image-Exp0.1_repackaged/resolve/main/split_files/text_encoders/jina_clip_v2_bf16.safetensors",
        "directory": f"{MODELS_BASE_PATH}/text_encoders"
    }
]

app = create_downloader_app("Downloader-NoobAI", NOOBAI_DOWNLOADS)