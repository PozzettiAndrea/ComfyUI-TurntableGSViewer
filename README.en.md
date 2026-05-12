# ComfyUI PlyPreview

[中文](README.md) | [English](README.en.md)

Gaussian Splat PLY loader + preview nodes for ComfyUI. Forked from GeometryPack and repackaged to avoid upstream overwrites. Includes front-end viewer (gsplat.js) bundled locally.

## Nodes
- Load Gaussian PLY — dropdown from `input/`, `input/3d`, `output/` with auto-resolution, FOV 10–180°, optional opacity filter.
- Load Gaussian PLY (Path) — manual path entry with the same camera/auto-res options.
- Process Gaussian PLY — accept upstream `ply_path` (e.g., SHARP Predict) with camera override/opacity filter.
- Preview Gaussian — gsplat.js WebGL viewer with scale slider, reset, screenshot, info panel.

## Features
- Auto resolution from FOV + target scale (rounded to 16px, calibration factor 0.8).
- Opacity filtering (sigmoid) with threshold.
- Camera intrinsics/extrinsics outputs for consistent preview.
- Wide FOV (10–180°) including fisheye cases.
- Fully self-contained: viewer HTML/JS bundled under `web/`.

## Install (Git clone)
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/XuanYu-github/comfyui-PlyPreview.git
```
Restart ComfyUI.

## Install (ComfyUI Manager)
Search for “comfyui-PlyPreview” in Manager and install. (This repo ships `comfyui_extension.json` so Manager can detect it.)

## Usage
1) Use one of the Load nodes or Process node to produce `ply_path`, `extrinsics`, `intrinsics`.
2) Connect to Preview Gaussian. After execution the viewer iframe shows controls (Scale, Reset View, Screenshot) and info panel.
3) If opacity filtering is enabled, a filtered PLY is written alongside the source (suffix `_opacity{threshold}.ply`).

## Requirements
- ComfyUI recent build with DOM widgets enabled (standard).
- Python deps: `plyfile`, `numpy` (install via your ComfyUI environment). Most ComfyUI setups already have numpy; install plyfile if missing: `pip install plyfile`.

## Notes
- WEB_DIRECTORY is set to `web` so ComfyUI loads the bundled frontend automatically.
- Namespaces are prefixed `PlyPreview*` to avoid collision with GeometryPack.
- Original GeometryPack license is GPL-3.0; this fork keeps the same license.

## License
GPL-3.0-or-later. See [LICENSE](LICENSE).
