# SPDX-License-Identifier: GPL-3.0-or-later

import os
from .common import (
    COMFYUI_INPUT_FOLDER,
    COMFYUI_OUTPUT_FOLDER,
    get_default_extrinsics,
    get_default_intrinsics,
    get_recommended_resolution,
)
from .load_gaussian_ply import LoadGaussianPLY


class LoadGaussianPLYPath:
    """Load a Gaussian splat PLY file by entering the path directly."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ply_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "Path to .ply file (absolute or relative to ComfyUI input/output folders)",
                }),
                "fov_degrees": ("FLOAT", {
                    "default": 50.0,
                    "min": 10.0,
                    "max": 180.0,
                    "step": 1.0,
                    "tooltip": "Horizontal field of view in degrees (10-180°, supports wide-angle and fisheye)",
                }),
                "auto_resolution": (["disabled", "enabled"], {
                    "default": "enabled",
                    "tooltip": "Auto-calculate optimal resolution based on FOV and target scale",
                }),
            },
            "optional": {
                "target_scale": ("FLOAT", {
                    "default": 10.0,
                    "min": 1.0,
                    "max": 50.0,
                    "step": 1.0,
                    "tooltip": "Target gaussian scale in viewer (used when auto_resolution enabled)",
                }),
                "image_width": ("INT", {
                    "default": 512,
                    "min": 64,
                    "max": 8192,
                    "step": 1,
                    "tooltip": "Image width for camera intrinsics (used when auto_resolution disabled)",
                }),
                "image_height": ("INT", {
                    "default": 512,
                    "min": 64,
                    "max": 8192,
                    "step": 1,
                    "tooltip": "Image height for camera intrinsics (used when auto_resolution disabled)",
                }),
                "enable_opacity_filter": (["disabled", "enabled"], {
                    "default": "disabled",
                    "tooltip": "Filter out low-opacity Gaussians to reduce background noise",
                }),
                "opacity_threshold": ("FLOAT", {
                    "default": 0.1,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                    "tooltip": "Minimum opacity (0-1). Gaussians below this will be removed (used when filter enabled)",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "EXTRINSICS", "INTRINSICS")
    RETURN_NAMES = ("ply_path", "extrinsics", "intrinsics")
    FUNCTION = "load_ply"
    CATEGORY = "PlyPreview"

    @classmethod
    def IS_CHANGED(cls, ply_path, **kwargs):
        resolved = cls._resolve_path(ply_path)
        if resolved and os.path.exists(resolved):
            return os.path.getmtime(resolved)
        return ply_path

    @classmethod
    def _resolve_path(cls, ply_path):
        if not ply_path:
            return None
        candidate = ply_path.strip().strip('"')
        if candidate == "":
            return None
        if os.path.isabs(candidate) and os.path.exists(candidate):
            return candidate
        if COMFYUI_OUTPUT_FOLDER is not None:
            output_candidate = os.path.join(COMFYUI_OUTPUT_FOLDER, candidate)
            if os.path.exists(output_candidate):
                return output_candidate
        if COMFYUI_INPUT_FOLDER is not None:
            input_candidate = os.path.join(COMFYUI_INPUT_FOLDER, candidate)
            if os.path.exists(input_candidate):
                return input_candidate
            input_3d_candidate = os.path.join(COMFYUI_INPUT_FOLDER, "3d", candidate)
            if os.path.exists(input_3d_candidate):
                return input_3d_candidate
        if os.path.exists(candidate):
            return candidate
        return None

    def load_ply(
        self,
        ply_path: str,
        fov_degrees: float = 50.0,
        auto_resolution: str = "enabled",
        target_scale: float = 10.0,
        image_width: int = 512,
        image_height: int = 512,
        enable_opacity_filter: str = "disabled",
        opacity_threshold: float = 0.1,
    ):
        if not ply_path or ply_path.strip() == "":
            raise ValueError("PLY path cannot be empty")

        resolved = self._resolve_path(ply_path)
        if resolved is None:
            searched = [ply_path]
            if COMFYUI_OUTPUT_FOLDER:
                searched.append(os.path.join(COMFYUI_OUTPUT_FOLDER, ply_path))
            if COMFYUI_INPUT_FOLDER:
                searched.append(os.path.join(COMFYUI_INPUT_FOLDER, ply_path))
                searched.append(os.path.join(COMFYUI_INPUT_FOLDER, "3d", ply_path))
            formatted = "\n".join(f"  - {path}" for path in searched)
            raise ValueError(f"PLY file not found. Searched in:\n{formatted}")

        if not resolved.lower().endswith(".ply"):
            raise ValueError("File must be a .ply Gaussian splat")

        print(f"[LoadGaussianPLYPath] Using PLY file: {resolved}")

        if auto_resolution == "enabled":
            image_width, image_height = get_recommended_resolution(fov_degrees, target_scale)
            print(f"[LoadGaussianPLYPath] Auto-resolution for FOV {fov_degrees}° @ scale {target_scale}: {image_width}x{image_height}")

        output_path = resolved
        if enable_opacity_filter == "enabled":
            loader = LoadGaussianPLY()
            output_path = loader._filter_by_opacity(resolved, opacity_threshold)
            print(f"[LoadGaussianPLYPath] Filtered PLY saved to: {output_path}")

        extrinsics = get_default_extrinsics()
        intrinsics = get_default_intrinsics(image_width, image_height, fov_degrees)
        print(f"[LoadGaussianPLYPath] Camera: FOV={fov_degrees}°, size={image_width}x{image_height}")

        return (output_path, extrinsics, intrinsics)
