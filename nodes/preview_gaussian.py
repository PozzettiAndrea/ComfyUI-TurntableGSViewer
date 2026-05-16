# SPDX-License-Identifier: GPL-3.0-or-later

import os

from .common import (
    COMFYUI_INPUT_FOLDER,
    COMFYUI_OUTPUT_FOLDER,
    get_default_extrinsics,
    get_default_intrinsics,
)


def _resolve_for_view(abs_path: str) -> tuple[str, str, str]:
    """Map an absolute on-disk PLY to ComfyUI's `/view` parameters.

    Returns (filename, subfolder, folder_kind) where folder_kind is one
    of "output" / "input" / "output" (fallback). The JS preview fetches
    `/view?filename=...&type=<kind>&subfolder=...`, which is keyed off
    `folder_paths.get_<kind>_directory()` on the server side.
    """
    bases = []
    if COMFYUI_OUTPUT_FOLDER:
        bases.append(("output", COMFYUI_OUTPUT_FOLDER))
    if COMFYUI_INPUT_FOLDER:
        bases.append(("input", COMFYUI_INPUT_FOLDER))

    for kind, base in bases:
        # normpath both sides so trailing slashes / .. don't trip startswith
        b = os.path.normpath(base) + os.sep
        a = os.path.normpath(abs_path)
        if a.startswith(b):
            rel = os.path.relpath(a, base)
            subfolder, filename = os.path.split(rel)
            return filename, subfolder.replace(os.sep, "/"), kind

    # Path lives outside both — `/view` will 404. Fall back to "output"
    # and emit a bare basename; user will need to copy the PLY into
    # ComfyUI/input/ or output/ for the previewer to reach it.
    return os.path.basename(abs_path), "", "output"


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
                "transport_format": (["ply", "spz"], {
                    "default": "ply",
                    "tooltip": (
                        "ply — lossless float32, ~225 MB for a 1M-splat SH=3 "
                        "scene. Slow to download but every SH3 highlight is "
                        "preserved bit-perfect from training. "
                        "\n"
                        "spz — server transcodes to SPZ v2 once and caches "
                        "next to the PLY. ~9x smaller (~25 MB), but SH2/SH3 "
                        "quantize to 4 bits each, which flattens specular "
                        "highlights. Use when bandwidth matters more than "
                        "view-dependent fidelity."
                    ),
                }),
            },
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "preview"
    CATEGORY = "viewer"

    def preview(self, ply_path, fov_degrees, image_width, image_height, renderer, transport_format="ply"):
        if not ply_path:
            return {"ui": {"error": ["No PLY path provided"]}}
        if not os.path.exists(ply_path):
            return {"ui": {"error": [f"File not found: {ply_path}"]}}

        filename, subfolder, folder_kind = _resolve_for_view(ply_path)

        file_size_mb = round(os.path.getsize(ply_path) / (1024 * 1024), 2)
        num_gaussians = _count_gaussians(ply_path)
        intrinsics = get_default_intrinsics(image_width, image_height, fov_degrees)
        extrinsics = get_default_extrinsics()

        return {"ui": {
            "ply_file": [filename],
            "filename": [filename],
            "ply_type": [folder_kind],         # "input" | "output" — JS passes to /view?type=
            "ply_subfolder": [subfolder],
            "file_size_mb": [file_size_mb],
            "num_gaussians": [num_gaussians],
            "extrinsics": [extrinsics],
            "intrinsics": [intrinsics],
            "fov_degrees": [fov_degrees],
            "renderer": [renderer],
            "transport_format": [transport_format],
        }}
