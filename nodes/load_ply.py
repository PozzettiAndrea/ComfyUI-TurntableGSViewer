# SPDX-License-Identifier: GPL-3.0-or-later

"""LoadPLY — file picker for 3D Gaussian Splatting PLY files.

Scans both `input/` and `output/` of the running ComfyUI instance so
users can pick PLYs they uploaded OR PLYs produced upstream (e.g. by
ComfyUI-Lito's `LiToExportPLY`) without copying files around. Output
is the absolute path, ready to wire into `PreviewGaussians` /
`GaussianMerge`.
"""

import logging
import os

log = logging.getLogger("comfyui-gaussianpack")


def _scan_ply_files() -> tuple[list[str], dict[str, str]]:
    """Walk ComfyUI's input/ and output/ for .ply files.

    Returns:
        (combo_entries, resolver):
            combo_entries — sorted list of "<kind>/<relpath>" strings
              displayed in the dropdown.
            resolver — combo entry -> absolute path on disk.
    """
    try:
        import folder_paths
    except ImportError:
        return ([], {})

    roots = {
        "input":  folder_paths.get_input_directory(),
        "output": folder_paths.get_output_directory(),
    }
    entries: list[str] = []
    resolver: dict[str, str] = {}
    for kind, base in roots.items():
        if not base or not os.path.isdir(base):
            continue
        for dirpath, _, names in os.walk(base):
            for name in names:
                if not name.lower().endswith(".ply"):
                    continue
                abs_path = os.path.join(dirpath, name)
                rel = os.path.relpath(abs_path, base).replace(os.sep, "/")
                key = f"{kind}/{rel}"
                entries.append(key)
                resolver[key] = abs_path
    entries.sort()
    return entries, resolver


class LoadPLY:
    """Browse a `.ply` file from ComfyUI's input/ or output/ directories."""

    @classmethod
    def INPUT_TYPES(cls):
        entries, _ = _scan_ply_files()
        if not entries:
            entries = ["<no .ply files found in input/ or output/>"]
        return {
            "required": {
                "ply_file": (entries, {
                    "tooltip": (
                        "Pick a .ply from ComfyUI's input/ or output/ folders. "
                        "LiTo's LiToExportPLY writes to output/, so its outputs "
                        "appear here directly. Drop your own PLYs into input/ "
                        "to make them appear in this list."
                    ),
                }),
            },
        }

    @classmethod
    def IS_CHANGED(cls, ply_file):
        """Re-execute the node if the picked file's mtime changes."""
        _, resolver = _scan_ply_files()
        path = resolver.get(ply_file)
        if path and os.path.exists(path):
            return str(os.path.getmtime(path))
        return ""

    @classmethod
    def VALIDATE_INPUTS(cls, ply_file):
        _, resolver = _scan_ply_files()
        if ply_file not in resolver:
            return f"LoadPLY: {ply_file!r} is not a known PLY in input/ or output/"
        return True

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("ply_path",)
    FUNCTION = "load"
    CATEGORY = "viewer"

    def load(self, ply_file: str):
        _, resolver = _scan_ply_files()
        path = resolver.get(ply_file)
        if not path or not os.path.exists(path):
            raise FileNotFoundError(f"LoadPLY: {ply_file!r} not found on disk")
        log.info("LoadPLY: %s -> %s", ply_file, path)
        return (path,)
