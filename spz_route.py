"""HTTP route that transcodes a PLY to SPZ on demand and serves it.

Registered into ComfyUI's aiohttp server (PromptServer.instance.routes).
The first request for a given PLY pays the conversion cost and writes a
sibling `.spz` next to the PLY; subsequent requests stream the cached SPZ
directly.

Query:
    /turntablegsviewer/spz?filename=<output-relative-name>&subfolder=<sub>
                          [&type=output]

Mirrors ComfyUI's /view endpoint shape so the JS side can build URLs the
same way it does today.
"""
import logging
import os
import threading
from pathlib import Path

from aiohttp import web

import folder_paths

log = logging.getLogger("comfyui-turntablegsviewer")

# Per-path lock so two concurrent requests for the same PLY don't both
# kick off the transcode in parallel.
_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _lock_for(p: str) -> threading.Lock:
    with _locks_lock:
        if p not in _locks:
            _locks[p] = threading.Lock()
        return _locks[p]


def _resolve_output_path(filename: str, subfolder: str, type_: str) -> Path | None:
    """Resolve a /view-style (filename, subfolder, type) to an absolute path,
    refusing anything that escapes the output directory."""
    base_dir = {
        "output": folder_paths.get_output_directory(),
        "input":  folder_paths.get_input_directory(),
        "temp":   folder_paths.get_temp_directory(),
    }.get(type_, folder_paths.get_output_directory())
    base = Path(base_dir).resolve()
    candidate = (base / (subfolder or "") / filename).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def _transcode_ply_to_spz(ply_path: Path, spz_path: Path) -> None:
    """Run the spz package's PLY → SPZ pipeline and write atomically."""
    import spz
    tmp = spz_path.with_suffix(spz_path.suffix + ".part")
    unpack = spz.UnpackOptions()
    cloud = spz.load_splat_from_ply(str(ply_path), unpack)
    pack = spz.PackOptions()
    ok = spz.save_spz(cloud, pack, str(tmp))
    if not ok:
        try: tmp.unlink()
        except FileNotFoundError: pass
        raise RuntimeError(f"spz.save_spz failed for {ply_path}")
    tmp.replace(spz_path)


def register_routes() -> None:
    """Register the /turntablegsviewer/spz route. Idempotent and a no-op
    if PromptServer isn't available (e.g. during static analysis)."""
    try:
        from server import PromptServer
    except ImportError:
        log.warning("PromptServer not importable; SPZ route not registered.")
        return
    if PromptServer.instance is None:
        log.warning("PromptServer.instance is None; SPZ route not registered.")
        return

    routes = PromptServer.instance.routes

    @routes.get("/turntablegsviewer/spz")
    async def get_spz(request: web.Request) -> web.StreamResponse:
        filename  = request.query.get("filename", "")
        subfolder = request.query.get("subfolder", "")
        type_     = request.query.get("type", "output")
        if not filename:
            return web.Response(status=400, text="missing 'filename'")
        if not filename.lower().endswith(".ply"):
            return web.Response(status=400, text="filename must end in .ply")

        ply = _resolve_output_path(filename, subfolder, type_)
        if ply is None:
            return web.Response(status=403, text="path traversal rejected")
        if not ply.is_file():
            return web.Response(status=404, text=f"PLY not found: {ply}")

        spz = ply.with_suffix(".spz")
        # Cache valid only if newer than the PLY.
        cache_fresh = spz.is_file() and spz.stat().st_mtime >= ply.stat().st_mtime

        if not cache_fresh:
            with _lock_for(str(spz)):
                # Re-check after acquiring the lock — someone else may have
                # finished while we were waiting.
                cache_fresh = spz.is_file() and spz.stat().st_mtime >= ply.stat().st_mtime
                if not cache_fresh:
                    log.info("SPZ cache miss; transcoding %s -> %s", ply.name, spz.name)
                    try:
                        _transcode_ply_to_spz(ply, spz)
                    except ImportError:
                        return web.Response(
                            status=500,
                            text=("'spz' package not installed in the ComfyUI env. "
                                  "Disable the 'Compress (SPZ)' toggle or "
                                  "`pip install spz`."),
                        )
                    except Exception as e:
                        log.exception("SPZ transcode failed for %s", ply)
                        return web.Response(status=500, text=f"SPZ transcode failed: {e}")
                    log.info(
                        "SPZ written: %s (%.1f MB → %.1f MB)",
                        spz.name,
                        ply.stat().st_size / (1024 * 1024),
                        spz.stat().st_size / (1024 * 1024),
                    )

        return web.FileResponse(
            spz,
            headers={
                "Content-Type": "application/octet-stream",
                "Cache-Control": "no-cache",
            },
        )
