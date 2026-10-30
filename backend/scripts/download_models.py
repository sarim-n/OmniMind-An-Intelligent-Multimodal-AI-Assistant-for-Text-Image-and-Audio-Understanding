"""Pre-download weights for the configured hardware profile from Hugging Face."""

import os
import sys

# Ensure backend root is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.core.logging import get_logger, setup_logging

setup_logging()
logger = get_logger("download_models")


def download_active_models() -> None:
    """Download models required for current PROFILE."""
    print("=" * 60)
    print(f"OMNIMIND MODEL PRE-DOWNLOAD (PROFILE: {settings.PROFILE})")
    print("=" * 60)

    from huggingface_hub import snapshot_download

    models_to_download = [
        ("Text Embedding", settings.effective_text_embedding_model),
        ("Image Embedding (SigLIP)", settings.effective_image_embedding_model),
        ("LLM", settings.effective_llm_model),
        ("VLM", settings.effective_vlm_model),
        ("Object Detector (RT-DETR)", settings.effective_detector_model),
    ]

    for model_type, model_id in models_to_download:
        print(f"\n[+] Downloading {model_type}: {model_id} ...")
        try:
            snapshot_download(repo_id=model_id)
            print(f"[✓] {model_id} downloaded successfully.")
        except Exception as e:
            print(f"[!] Warning: failed downloading {model_id}: {e}")

    # Download ASR model via faster-whisper
    asr_model = settings.effective_asr_model
    print(f"\n[+] Downloading ASR (faster-whisper): {asr_model} ...")
    try:
        from faster_whisper import download_model

        download_model(asr_model)
        print(f"[✓] faster-whisper '{asr_model}' downloaded successfully.")
    except Exception as e:
        print(f"[!] Warning: failed downloading ASR model {asr_model}: {e}")

    print("\nModel pre-download complete!")


if __name__ == "__main__":
    download_active_models()
