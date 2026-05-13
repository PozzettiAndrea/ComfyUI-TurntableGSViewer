#!/usr/bin/env python3
"""Playwright harness that drives viewer_gaussian.html in headless Chromium and
prints diagnostics about why the canvas may be blank.

usage:  python3 debug_viewer.py [path/to/file.ply]
"""
import json
import mimetypes
import os
import pathlib
import socketserver
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
VIEWER_DIR = (HERE.parent / "web").resolve()
PLY_PATH = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(
    "/home/work/lito/ComfyUI/output/lito_output.ply"
)
PORT = 18432

# Allow the .ply route to map to PLY_PATH.
mimetypes.add_type("application/octet-stream", ".ply")


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, p):
        # Route /test.ply to our outside-the-webdir file.
        clean = p.split("?", 1)[0]
        if clean == "/test.ply":
            return str(PLY_PATH)
        return super().translate_path(p)

    def log_message(self, fmt, *args):
        pass  # silence


def start_server():
    Handler.directory = str(VIEWER_DIR)

    class _H(Handler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(VIEWER_DIR), **kw)

    httpd = socketserver.TCPServer(("127.0.0.1", PORT), _H)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    print(f"[harness] static server: http://127.0.0.1:{PORT}/")
    return httpd


def main():
    if not PLY_PATH.exists():
        print(f"[harness] PLY not found: {PLY_PATH}")
        sys.exit(1)
    print(f"[harness] PLY: {PLY_PATH}  ({PLY_PATH.stat().st_size / 1e6:.1f} MB)")
    print(f"[harness] viewer: {VIEWER_DIR}")
    httpd = start_server()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--use-gl=swiftshader", "--ignore-gpu-blocklist", "--enable-webgl"],
        )
        ctx = browser.new_context(viewport={"width": 1024, "height": 768})
        page = ctx.new_page()

        def on_console(m):
            t = m.type
            tag = f"[{t}]" if t != "log" else ""
            print(f"  {tag} {m.text}")

        page.on("console", on_console)
        page.on("pageerror", lambda e: print(f"  [pageerror] {e}"))

        print("[harness] navigating to viewer...")
        page.goto(f"http://127.0.0.1:{PORT}/viewer_gaussian.html",
                  wait_until="load", timeout=30000)
        page.wait_for_function("typeof window.__gs === 'object'")

        print("[harness] sending LOAD_MESH_DATA...")
        t0 = time.monotonic()
        page.evaluate("""async () => {
            window._mesh_loaded = false;
            window._mesh_error  = null;
            window.addEventListener('message', e => {
                if (e.data && e.data.type === 'MESH_LOADED') window._mesh_loaded = true;
                if (e.data && e.data.type === 'MESH_ERROR')  window._mesh_error  = e.data.error;
            });
            const resp = await fetch('/test.ply');
            if (!resp.ok) throw new Error('fetch /test.ply failed: ' + resp.status);
            const buf = await resp.arrayBuffer();
            window.postMessage({
                type: 'LOAD_MESH_DATA',
                data: buf,
                filename: 'test.ply',
                renderer: 'webgl2',
            }, '*');
        }""")
        print("[harness] waiting for load (timeout 180s)...")
        try:
            page.wait_for_function("window._mesh_loaded || window._mesh_error",
                                   timeout=180000)
        except Exception as e:
            print(f"[harness] TIMED OUT waiting for load: {e}")
        err = page.evaluate("window._mesh_error")
        if err:
            print(f"[harness] viewer reported MESH_ERROR: {err}")
        print(f"[harness] roundtrip: {time.monotonic() - t0:.1f} s")

        # Pump frames for a moment so any deferred upload finishes.
        page.wait_for_timeout(2500)

        state = page.evaluate("window.__gs.state()")
        print("[harness] viewer state:\n" + json.dumps(state, indent=2))

        # ---- Probe: pixel histogram ---------------------------------
        hist_js = """() => {
            const c = document.getElementById('canvas');
            const gl = c.getContext('webgl2') || c.getContext('webgl');
            if (!gl) return { error: 'no gl context' };
            const w = c.width, h = c.height;
            const pixels = new Uint8Array(w * h * 4);
            gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
            let nonBlack = 0, rSum = 0, gSum = 0, bSum = 0, aSum = 0, max = 0;
            for (let i = 0; i < pixels.length; i += 4) {
                const r = pixels[i], g = pixels[i+1], b = pixels[i+2], a = pixels[i+3];
                if (r > 30 || g > 30 || b > 30) nonBlack++;
                const m = Math.max(r, g, b);
                if (m > max) max = m;
                rSum += r; gSum += g; bSum += b; aSum += a;
            }
            const total = pixels.length / 4;
            return {
                wh: [w, h],
                client: [c.clientWidth, c.clientHeight],
                nonBlackPx: nonBlack,
                totalPx: total,
                nonBlackPct: +(nonBlack / total * 100).toFixed(2),
                avg: [rSum / total, gSum / total, bSum / total, aSum / total].map(v => +v.toFixed(2)),
                max,
                ctxLost: gl.isContextLost(),
                vendor: gl.getParameter(gl.VENDOR),
                renderer: gl.getParameter(gl.RENDERER),
            };
        }"""
        print("[harness] pixel histogram:\n" +
              json.dumps(page.evaluate(hist_js), indent=2))

        # ---- Probe: splat data ------------------------------------
        splat_js = r"""
            if (!splatMesh) return { error: "no splatMesh" };
            const n = splatMesh.getSplatCount();
            if (!n) return { error: "splatCount 0" };
            const v = new THREE.Vector3();
            const c = new Uint8Array(4);
            const out = { n };
            const idxs = [0, Math.floor(n/4), Math.floor(n/2), Math.floor(3*n/4), n-1];
            out.samples = idxs.map(i => {
                let pos = null, col = null, err = null;
                try { splatMesh.getSplatCenter(i, v); pos = [v.x, v.y, v.z]; } catch (e) { err = 'center: ' + e.message; }
                try { splatMesh.getSplatColor(i, c);  col = [c[0], c[1], c[2], c[3]]; } catch (e) { err = (err ? err + '; ' : '') + 'color: ' + e.message; }
                return { i, pos, col, err };
            });
            try {
                const sb = splatMesh.splatBuffer || (splatMesh.splatBuffers && splatMesh.splatBuffers[0]);
                if (sb) {
                    out.splatBufferKeys = Object.keys(sb).filter(k => !k.startsWith('_')).slice(0, 60);
                    out.minSHDegree = sb.minSphericalHarmonicsDegree;
                    out.maxSHDegree = sb.maxSphericalHarmonicsDegree;
                    out.outSHDegree = sb.outSphericalHarmonicsDegree;
                    out.sceneCount  = sb.getSceneCount && sb.getSceneCount();
                    out.splatCount  = sb.getSplatCount && sb.getSplatCount();
                }
            } catch (e) { out.splatBufferErr = e.message; }
            try {
                const mat = splatMesh.material;
                out.matType = mat && mat.type;
                out.matVisible = mat && mat.visible;
                out.matTransparent = mat && mat.transparent;
                out.uniforms = mat && mat.uniforms ? Object.keys(mat.uniforms) : null;
                out.matVertexShaderLen = mat && mat.vertexShader && mat.vertexShader.length;
                out.matFragmentShaderLen = mat && mat.fragmentShader && mat.fragmentShader.length;
                out.matProgram = !!(mat && mat.program);
            } catch (e) { out.matErr = e.message; }
            try {
                out.meshVisible = splatMesh.visible;
                out.meshInScene = !!splatMesh.parent;
                out.meshParentType = splatMesh.parent && splatMesh.parent.type;
                out.meshPos = [splatMesh.position.x, splatMesh.position.y, splatMesh.position.z];
                const bb = splatMesh.geometry && splatMesh.geometry.boundingBox;
                out.geomBB = bb ? { min: bb.min.toArray(), max: bb.max.toArray() } : null;
            } catch (e) { out.meshErr = e.message; }
            return out;
        """
        print("[harness] splat probe:\n" +
              json.dumps(page.evaluate(f"window.__gs.run({json.dumps(splat_js)})"), indent=2))

        # ---- Probe: scene walk ------------------------------------
        scene_js = r"""
            const scene = viewer && viewer.threeScene;
            if (!scene) return { error: "no threeScene" };
            const out = { childCount: scene.children.length, children: [] };
            scene.traverse((o) => {
                out.children.push({
                    type: o.type, name: o.name, visible: o.visible,
                    pos: [o.position.x, o.position.y, o.position.z],
                });
            });
            return out;
        """
        print("[harness] scene:\n" +
              json.dumps(page.evaluate(f"window.__gs.run({json.dumps(scene_js)})"), indent=2))

        # Screenshot of the iframe / page.
        shot = "/tmp/viewer_debug.png"
        page.screenshot(path=shot, full_page=False)
        print(f"[harness] screenshot: {shot}")

        browser.close()
    httpd.shutdown()


if __name__ == "__main__":
    main()
