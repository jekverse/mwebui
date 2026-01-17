import modal
import io
import os
import time
from fastapi import Response

# Definisikan nama model
MODEL_ID = "Qwen/Qwen-Image-2512"


def download_model_to_image():
    from diffusers import DiffusionPipeline
    import torch
    from huggingface_hub import snapshot_download
    
    print("🏗️ BUILDING IMAGE: Downloading Model ke Local Storage...")
    # Kita gunakan snapshot_download agar file ter-cache di layer image
    snapshot_download(MODEL_ID)
    print("✅ Model baked into image!")

# 1. Definisi Image
qwen_image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install(
        "fastapi", "diffusers", "transformers", "accelerate", 
        "safetensors", "sentencepiece", "protobuf", "torch", "hf_transfer"
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
    .run_function(download_model_to_image)
)

app = modal.App("qwen-image-baked-ssd")

@app.cls(
    image=qwen_image,
    gpu="H100",
    scaledown_window=60, 
    timeout=600,
    # HAPUS volumes={...} & enable_memory_snapshot=True
)
class QwenModel:
    @modal.enter()
    def load_weights(self):
        from diffusers import DiffusionPipeline
        import torch

        print(f"🚀 [SSD Load] Memuat model dari Local NVMe Cache...")
        start_load = time.perf_counter()
        
        # Karena sudah di-download saat build, ini akan load dari disk lokal (sangat cepat)
        self.pipe = DiffusionPipeline.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.bfloat16,
            local_files_only=True # Pastikan tidak connect internet
        ).to("cuda")
        
        duration = time.perf_counter() - start_load
        print(f"✅ Model Loaded dalam {duration:.2f} detik (Speed: {40/duration:.2f} GB/s)")

    @modal.fastapi_endpoint(method="POST")
    def generate(self, item: dict):
        import torch
        
        prompt = item.get("prompt", "")
        neg_prompt = item.get("negative_prompt", "low quality")
        width = item.get("width", 1024)
        height = item.get("height", 1024)
        
        print(f"🎨 Generating Prompt: {prompt[:30]}...")

        image = self.pipe(
            prompt=prompt,
            negative_prompt=neg_prompt,
            width=width,
            height=height,
            num_inference_steps=50,
            true_cfg_scale=4.0,
            generator=torch.Generator(device="cuda").manual_seed(42)
        ).images[0]
        
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        
        return Response(content=buf.getvalue(), media_type="image/png")