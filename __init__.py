# SPDX-License-Identifier: GPL-3.0-or-later

"""ComfyUI-GaussianPack — Gaussian-splat preview + target-count merging."""

from .preview_gaussian import PreviewGaussians
from .merge_gaussians import GaussianMerge
from .spz_route import register_routes as _register_spz_route

_register_spz_route()

WEB_DIRECTORY = "web"

NODE_CLASS_MAPPINGS = {
    "PreviewGaussians": PreviewGaussians,
    "GaussianMerge": GaussianMerge,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PreviewGaussians": "Preview Gaussians",
    "GaussianMerge": "Gaussian Merge to Target",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
