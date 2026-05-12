# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 comfyui-PlyPreview Contributors

"""ComfyUI PLY Preview - Gaussian splat PLY file loading and preview nodes."""

from .load_gaussian_ply import LoadGaussianPLY
from .load_gaussian_ply_path import LoadGaussianPLYPath
from .process_gaussian_ply import ProcessGaussianPLY
from .preview_gaussian import PreviewGaussianNode
from aiohttp import web

try:
    from server import PromptServer
except Exception as e:  # pragma: no cover - ComfyUI runtime only
    PromptServer = None
    print(f"[PlyPreview] Warning: server import failed: {e}")

WEB_DIRECTORY = "web"

NODE_CLASS_MAPPINGS = {
    "PlyPreviewLoadGaussianPLYEnhance": LoadGaussianPLY,
    "PlyPreviewLoadGaussianPLYPathEnhance": LoadGaussianPLYPath,
    "PlyPreviewProcessGaussianPLYEnhance": ProcessGaussianPLY,
    "PlyPreviewPreviewGaussianEnhance": PreviewGaussianNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PlyPreviewLoadGaussianPLYEnhance": "Load Gaussian PLY Enhance",
    "PlyPreviewLoadGaussianPLYPathEnhance": "Load Gaussian PLY (Path) Enhance",
    "PlyPreviewProcessGaussianPLYEnhance": "Process Gaussian PLY Enhance",
    "PlyPreviewPreviewGaussianEnhance": "Preview Gaussian Enhance",
}

# Lightweight API to let the frontend refresh PLY dropdowns without restarting ComfyUI
if PromptServer is not None:
    async def plypreview_list_ply_files(request):  # pragma: no cover - runtime route
        files = LoadGaussianPLY._get_ply_files()
        return web.json_response({"files": files})

    try:
        PromptServer.instance.routes.get("/plypreview/files")(plypreview_list_ply_files)
        print("[PlyPreview] Registered /plypreview/files refresh endpoint")
    except Exception as e:  # pragma: no cover
        print(f"[PlyPreview] Warning: failed to register refresh endpoint: {e}")

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "LoadGaussianPLY",
    "LoadGaussianPLYPath",
    "ProcessGaussianPLY",
    "PreviewGaussianNode",
]
