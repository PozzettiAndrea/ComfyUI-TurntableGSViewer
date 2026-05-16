"""ComfyUI-GaussianPack Prestartup Script."""

from pathlib import Path

from comfy_env import copy_files

SCRIPT_DIR = Path(__file__).resolve().parent
COMFYUI_DIR = SCRIPT_DIR.parent.parent

# Copy bundled example assets (apple.ply, ...) into ComfyUI's input/ so
# workflows that reference them by basename work on a fresh install.
# copy_files() is non-clobbering — pre-existing files in input/ are left
# alone so user edits aren't overwritten on restart.
copy_files(SCRIPT_DIR / "assets", COMFYUI_DIR / "input", "**/*")
