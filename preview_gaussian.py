# SPDX-License-Identifier: GPL-3.0-or-later

import os
from .common import COMFYUI_OUTPUT_FOLDER


class PreviewGaussianNode:
    """Preview Gaussian Splatting PLY files in an interactive gsplat.js viewer."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ply_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Path to a Gaussian Splatting PLY file",
                }),
            },
            "optional": {
                "extrinsics": ("EXTRINSICS", {
                    "tooltip": "4x4 camera extrinsics matrix for initial view",
                }),
                "intrinsics": ("INTRINSICS", {
                    "tooltip": "3x3 camera intrinsics matrix for FOV",
                }),
            },
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "preview_gaussian"
    CATEGORY = "PlyPreview/visualization"

    def preview_gaussian(self, ply_path: str, extrinsics=None, intrinsics=None):
        if not ply_path:
            print("[PreviewGaussian] No PLY path provided")
            return {"ui": {"error": ["No PLY path provided"]}}

        if not os.path.exists(ply_path):
            print(f"[PreviewGaussian] PLY file not found: {ply_path}")
            return {"ui": {"error": [f"File not found: {ply_path}"]}}

        filename = os.path.basename(ply_path)

        if COMFYUI_OUTPUT_FOLDER and ply_path.startswith(COMFYUI_OUTPUT_FOLDER):
            relative_path = os.path.relpath(ply_path, COMFYUI_OUTPUT_FOLDER)
        else:
            relative_path = filename

        file_size = os.path.getsize(ply_path)
        file_size_mb = file_size / (1024 * 1024)

        print(f"[PreviewGaussian] Loading PLY: {filename} ({file_size_mb:.2f} MB)")

        ui_data: dict[str, list] = {
            "ply_file": [relative_path],
            "filename": [filename],
            "file_size_mb": [round(file_size_mb, 2)],
        }

        if extrinsics is not None:
            ui_data["extrinsics"] = [extrinsics]
        if intrinsics is not None:
            ui_data["intrinsics"] = [intrinsics]

        return {"ui": ui_data}
