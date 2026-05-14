# SPDX-License-Identifier: GPL-3.0-or-later

"""ComfyUI-GSViewer — tiny Gaussian-splat turntable viewer node."""

from .preview_gaussian import PreviewGaussians
from .spz_route import register_routes as _register_spz_route

_register_spz_route()

WEB_DIRECTORY = "web"

NODE_CLASS_MAPPINGS = {
    "PreviewGaussians": PreviewGaussians,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PreviewGaussians": "Preview Gaussians Turntable",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
