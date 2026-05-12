# SPDX-License-Identifier: GPL-3.0-or-later

import os
from .common import get_default_extrinsics, get_default_intrinsics, get_recommended_resolution
from .load_gaussian_ply import LoadGaussianPLY


class ProcessGaussianPLY:
    """Process a Gaussian splat PLY file from upstream nodes (e.g., SHARP Predict)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ply_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": "PLY file path from upstream node (e.g., SHARP Predict)",
                }),
            },
            "optional": {
                "input_extrinsics": ("EXTRINSICS", {
                    "tooltip": "Extrinsics from upstream node (ignored if override_camera enabled)",
                }),
                "input_intrinsics": ("INTRINSICS", {
                    "tooltip": "Intrinsics from upstream node (ignored if override_camera enabled)",
                }),
                "override_camera": (["disabled", "enabled"], {
                    "default": "enabled",
                    "tooltip": "Override input camera params with custom FOV settings",
                }),
                "fov_degrees": ("FLOAT", {
                    "default": 50.0,
                    "min": 10.0,
                    "max": 180.0,
                    "step": 1.0,
                    "tooltip": "Horizontal field of view in degrees (used when override_camera enabled)",
                }),
                "auto_resolution": (["disabled", "enabled"], {
                    "default": "enabled",
                    "tooltip": "Auto-calculate optimal resolution based on FOV and target scale",
                }),
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
                    "tooltip": "Image width (used when auto_resolution disabled)",
                }),
                "image_height": ("INT", {
                    "default": 512,
                    "min": 64,
                    "max": 8192,
                    "step": 1,
                    "tooltip": "Image height (used when auto_resolution disabled)",
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
                    "tooltip": "Minimum opacity (0-1). Gaussians below this will be removed",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "EXTRINSICS", "INTRINSICS")
    RETURN_NAMES = ("ply_path", "extrinsics", "intrinsics")
    FUNCTION = "process_ply"
    CATEGORY = "PlyPreview"

    def process_ply(
        self,
        ply_path: str,
        input_extrinsics=None,
        input_intrinsics=None,
        override_camera: str = "enabled",
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

        resolved = ply_path.strip().strip('"')
        if not os.path.exists(resolved):
            raise ValueError(f"PLY file not found: {resolved}")
        if not resolved.lower().endswith(".ply"):
            raise ValueError("File must be a .ply Gaussian splat")

        print(f"[ProcessGaussianPLY] Input PLY: {resolved}")

        if override_camera == "enabled":
            if auto_resolution == "enabled":
                image_width, image_height = get_recommended_resolution(fov_degrees, target_scale)
                print(f"[ProcessGaussianPLY] Auto-resolution for FOV {fov_degrees}° @ scale {target_scale}: {image_width}x{image_height}")
            extrinsics = get_default_extrinsics()
            intrinsics = get_default_intrinsics(image_width, image_height, fov_degrees)
            print(f"[ProcessGaussianPLY] Override camera: FOV={fov_degrees}°, size={image_width}x{image_height}")
        else:
            if input_extrinsics is not None:
                extrinsics = input_extrinsics
                print("[ProcessGaussianPLY] Using input extrinsics")
            else:
                extrinsics = get_default_extrinsics()
                print("[ProcessGaussianPLY] Using default extrinsics (no input provided)")

            if input_intrinsics is not None:
                intrinsics = input_intrinsics
                print("[ProcessGaussianPLY] Using input intrinsics")
            else:
                intrinsics = get_default_intrinsics(image_width, image_height, fov_degrees)
                print("[ProcessGaussianPLY] Using default intrinsics (no input provided)")

        output_path = resolved
        if enable_opacity_filter == "enabled":
            loader = LoadGaussianPLY()
            output_path = loader._filter_by_opacity(resolved, opacity_threshold)
            print(f"[ProcessGaussianPLY] Filtered PLY saved to: {output_path}")

        return (output_path, extrinsics, intrinsics)
