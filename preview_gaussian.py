# SPDX-License-Identifier: GPL-3.0-or-later

import os

from .common import (
    COMFYUI_OUTPUT_FOLDER,
    get_default_extrinsics,
    get_default_intrinsics,
)


def _count_gaussians(path: str) -> int:
    """Cheap header-only read of the splat count from a PLY. Returns 0 if
    the file isn't a PLY or the header can't be parsed."""
    if not path.lower().endswith(".ply"):
        return 0
    try:
        with open(path, "rb") as f:
            buf = f.read(8192).decode("latin-1", errors="replace")
        for line in buf.split("\n"):
            if line.startswith("element vertex "):
                return int(line.split()[2])
    except (OSError, ValueError, IndexError):
        return 0
    return 0


class PreviewGaussians:
    """Interactive Gaussian-splat turntable viewer (gsplat.js)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ply_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Path to a Gaussian Splatting PLY file",
                }),
                "fov_degrees": ("FLOAT", {
                    "default": 50.0, "min": 5.0, "max": 170.0, "step": 1.0,
                    "tooltip": "Vertical field of view in degrees",
                }),
                "image_width": ("INT", {
                    "default": 512, "min": 64, "max": 4096, "step": 8,
                }),
                "image_height": ("INT", {
                    "default": 512, "min": 64, "max": 4096, "step": 8,
                }),
                "renderer": (["spark", "playcanvas"], {
                    "default": "spark",
                    "tooltip": (
                        "spark — Three.js + WebGL2. Best SH3 fidelity, "
                        "auto-detects all formats (PLY, compressed.ply, SPZ, "
                        "KSPLAT, SOG, SPLAT). "
                        "\n"
                        "playcanvas — WebGPU path (currently falls back to "
                        "spark; real adapter pending). Will win on large "
                        "scenes (5M+ splats) when implemented."
                    ),
                }),
            },
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "preview"
    CATEGORY = "viewer"

    def preview(self, ply_path, fov_degrees, image_width, image_height, renderer):
        if not ply_path:
            return {"ui": {"error": ["No PLY path provided"]}}
        if not os.path.exists(ply_path):
            return {"ui": {"error": [f"File not found: {ply_path}"]}}

        filename = os.path.basename(ply_path)
        if COMFYUI_OUTPUT_FOLDER and ply_path.startswith(COMFYUI_OUTPUT_FOLDER):
            relative_path = os.path.relpath(ply_path, COMFYUI_OUTPUT_FOLDER)
        else:
            relative_path = filename

        file_size_mb = round(os.path.getsize(ply_path) / (1024 * 1024), 2)
        num_gaussians = _count_gaussians(ply_path)
        intrinsics = get_default_intrinsics(image_width, image_height, fov_degrees)
        extrinsics = get_default_extrinsics()

        return {"ui": {
            "ply_file": [relative_path],
            "filename": [filename],
            "file_size_mb": [file_size_mb],
            "num_gaussians": [num_gaussians],
            "extrinsics": [extrinsics],
            "intrinsics": [intrinsics],
            "fov_degrees": [fov_degrees],
            "renderer": [renderer],
        }}
