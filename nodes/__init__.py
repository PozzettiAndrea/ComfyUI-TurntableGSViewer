# SPDX-License-Identifier: GPL-3.0-or-later

"""GaussianPack nodes — preview, merge, and load PLY-format 3D Gaussian splats.

The root `__init__.py` calls `comfy_env.register_nodes()`, which imports
this module and harvests its `NODE_CLASS_MAPPINGS` /
`NODE_DISPLAY_NAME_MAPPINGS`. `WEB_DIRECTORY` is set at the root, not here.
"""

from .preview_gaussian import PreviewGaussians
from .merge_gaussians import GaussianMerge
from .load_ply import LoadPLY
from .spz_route import register_routes as _register_spz_route

_register_spz_route()

NODE_CLASS_MAPPINGS = {
    "PreviewGaussians": PreviewGaussians,
    "GaussianMerge": GaussianMerge,
    "LoadPLY": LoadPLY,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PreviewGaussians": "Preview Gaussians",
    "GaussianMerge": "Gaussian Merge to Target",
    "LoadPLY": "Load PLY",
}
