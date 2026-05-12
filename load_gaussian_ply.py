# SPDX-License-Identifier: GPL-3.0-or-later

import os
from .common import (
    COMFYUI_INPUT_FOLDER,
    COMFYUI_OUTPUT_FOLDER,
    get_default_extrinsics,
    get_default_intrinsics,
    get_recommended_resolution,
)


class LoadGaussianPLY:
    """Select a Gaussian splat PLY file from input/output folders or upload one."""

    @classmethod
    def INPUT_TYPES(cls):
        ply_files = cls._get_ply_files()
        if not ply_files:
            ply_files = ["No PLY files found"]

        return {
            "required": {
                "ply_file": (sorted(ply_files), {
                    "tooltip": "Select a .ply file from input or output folder, or upload one",
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
    def _get_ply_files(cls) -> list[str]:
        ply_files: list[str] = []

        if COMFYUI_INPUT_FOLDER and os.path.isdir(COMFYUI_INPUT_FOLDER):
            for f in os.listdir(COMFYUI_INPUT_FOLDER):
                full_path = os.path.join(COMFYUI_INPUT_FOLDER, f)
                if os.path.isfile(full_path) and f.lower().endswith(".ply"):
                    ply_files.append(f"[input] {f}")

            input_3d = os.path.join(COMFYUI_INPUT_FOLDER, "3d")
            if os.path.isdir(input_3d):
                for f in os.listdir(input_3d):
                    full_path = os.path.join(input_3d, f)
                    if os.path.isfile(full_path) and f.lower().endswith(".ply"):
                        ply_files.append(f"[input/3d] {f}")

        if COMFYUI_OUTPUT_FOLDER and os.path.isdir(COMFYUI_OUTPUT_FOLDER):
            for f in os.listdir(COMFYUI_OUTPUT_FOLDER):
                full_path = os.path.join(COMFYUI_OUTPUT_FOLDER, f)
                if os.path.isfile(full_path) and f.lower().endswith(".ply"):
                    ply_files.append(f"[output] {f}")

        return ply_files

    @classmethod
    def _resolve_selection(cls, selection: str) -> str | None:
        if not selection or selection == "No PLY files found":
            return None

        if selection.startswith("[input/3d] "):
            filename = selection[len("[input/3d] "):]
            if COMFYUI_INPUT_FOLDER:
                return os.path.join(COMFYUI_INPUT_FOLDER, "3d", filename)
        elif selection.startswith("[input] "):
            filename = selection[len("[input] "):]
            if COMFYUI_INPUT_FOLDER:
                return os.path.join(COMFYUI_INPUT_FOLDER, filename)
        elif selection.startswith("[output] "):
            filename = selection[len("[output] "):]
            if COMFYUI_OUTPUT_FOLDER:
                return os.path.join(COMFYUI_OUTPUT_FOLDER, filename)
        else:
            if COMFYUI_INPUT_FOLDER:
                candidate = os.path.join(COMFYUI_INPUT_FOLDER, selection)
                if os.path.exists(candidate):
                    return candidate
            if COMFYUI_OUTPUT_FOLDER:
                candidate = os.path.join(COMFYUI_OUTPUT_FOLDER, selection)
                if os.path.exists(candidate):
                    return candidate
        return None

    def _filter_by_opacity(self, ply_path: str, threshold: float) -> str:
        try:
            from plyfile import PlyData, PlyElement
            import numpy as np
        except ImportError:
            print("[LoadGaussianPLY] Warning: plyfile not installed, skipping opacity filter")
            return ply_path

        try:
            plydata = PlyData.read(ply_path)
            vertex = plydata["vertex"]

            field_names = vertex.data.dtype.names
            print(f"[LoadGaussianPLY] PLY fields: {field_names}")

            if "opacity" in field_names:
                opacity = np.array(vertex["opacity"])
                opacity = 1.0 / (1.0 + np.exp(-opacity))
                print(f"[LoadGaussianPLY] Opacity range after sigmoid: [{opacity.min():.4f}, {opacity.max():.4f}]")
            else:
                print(f"[LoadGaussianPLY] Warning: No 'opacity' field found in {list(field_names)}")
                return ply_path

            mask = opacity >= threshold
            n_original = len(opacity)
            n_filtered = int(np.sum(mask))
            print(f"[LoadGaussianPLY] Opacity filter: threshold={threshold:.3f}, kept {n_filtered}/{n_original} gaussians ({100*n_filtered/n_original:.1f}%)")

            if n_filtered == n_original or n_filtered == 0:
                if n_filtered == 0:
                    print("[LoadGaussianPLY] Warning: All gaussians filtered out! Using original file")
                else:
                    print("[LoadGaussianPLY] All gaussians passed filter, using original file")
                return ply_path

            filtered_arrays = []
            for prop in vertex.data.dtype.names:
                filtered_arrays.append(vertex[prop][mask])

            filtered_data = np.empty(n_filtered, dtype=vertex.data.dtype)
            for i, prop in enumerate(vertex.data.dtype.names):
                filtered_data[prop] = filtered_arrays[i]

            filtered_vertex = PlyElement.describe(filtered_data, "vertex")

            base_name = os.path.basename(ply_path)
            name_without_ext = os.path.splitext(base_name)[0]
            output_folder = os.path.dirname(ply_path)
            output_path = os.path.join(output_folder, f"{name_without_ext}_opacity{threshold:.2f}.ply")

            PlyData([filtered_vertex], text=False).write(output_path)
            print(f"[LoadGaussianPLY] Saved filtered PLY: {output_path}")
            return output_path
        except Exception as e:
            print(f"[LoadGaussianPLY] Error filtering PLY: {e}")
            return ply_path

    @classmethod
    def IS_CHANGED(cls, ply_file: str, **kwargs):
        resolved = cls._resolve_selection(ply_file)
        if resolved and os.path.exists(resolved):
            return os.path.getmtime(resolved)
        return ply_file

    @classmethod
    def VALIDATE_INPUTS(cls, ply_file: str, **kwargs):
        if not ply_file or ply_file == "No PLY files found":
            return "No PLY file selected"
        resolved = cls._resolve_selection(ply_file)
        if resolved is None or not os.path.exists(resolved):
            return f"PLY file not found: {ply_file}"
        return True

    def load_ply(
        self,
        ply_file: str,
        fov_degrees: float = 50.0,
        auto_resolution: str = "enabled",
        target_scale: float = 10.0,
        image_width: int = 512,
        image_height: int = 512,
        enable_opacity_filter: str = "disabled",
        opacity_threshold: float = 0.1,
    ):
        if not ply_file or ply_file == "No PLY files found":
            raise ValueError("No PLY file selected")

        resolved = self._resolve_selection(ply_file)
        if resolved is None:
            raise ValueError(f"Could not resolve PLY file: {ply_file}")
        if not os.path.exists(resolved):
            raise ValueError(f"PLY file not found: {resolved}")

        print(f"[LoadGaussianPLY] Selected: {ply_file}")
        print(f"[LoadGaussianPLY] Resolved path: {resolved}")

        if auto_resolution == "enabled":
            image_width, image_height = get_recommended_resolution(fov_degrees, target_scale)
            print(f"[LoadGaussianPLY] Auto-resolution for FOV {fov_degrees}° @ scale {target_scale}: {image_width}x{image_height}")

        output_path = resolved
        if enable_opacity_filter == "enabled":
            output_path = self._filter_by_opacity(resolved, opacity_threshold)
            print(f"[LoadGaussianPLY] Filtered PLY saved to: {output_path}")

        extrinsics = get_default_extrinsics()
        intrinsics = get_default_intrinsics(image_width, image_height, fov_degrees)
        print(f"[LoadGaussianPLY] Camera: FOV={fov_degrees}°, size={image_width}x{image_height}")

        return (output_path, extrinsics, intrinsics)
