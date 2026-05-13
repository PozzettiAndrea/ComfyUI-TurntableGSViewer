#!/usr/bin/env python3
"""Monkey-patch updateRenderIndexes to log every call, then force a sort and
see what the renderer sees. Also try directly setting drawRange ourselves."""
import json, sys, time, pathlib, socketserver, threading
from http.server import SimpleHTTPRequestHandler
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
VIEWER_DIR = (HERE.parent / "web").resolve()
PLY_PATH = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(
    "/home/work/lito/ComfyUI/output/lito_output.ply"
)
PORT = 18436

class _H(SimpleHTTPRequestHandler):
    def translate_path(self, p):
        if p.split("?",1)[0] == "/test.ply": return str(PLY_PATH)
        return super().translate_path(p)
    def log_message(self, *a): pass
    def __init__(self, *a, **kw): super().__init__(*a, directory=str(VIEWER_DIR), **kw)

PATCH_JS = r"""
window.__patchLog = [];
const origURI = splatMesh.updateRenderIndexes.bind(splatMesh);
splatMesh.updateRenderIndexes = function (globalIndexes, renderSplatCount) {
    const before = { start: splatMesh.geometry.drawRange.start, count: splatMesh.geometry.drawRange.count };
    let err = null;
    try {
        origURI(globalIndexes, renderSplatCount);
    } catch (e) {
        err = e.message;
    }
    const after = { start: splatMesh.geometry.drawRange.start, count: splatMesh.geometry.drawRange.count };
    window.__patchLog.push({
        renderSplatCount,
        globalIndexesLen: globalIndexes && globalIndexes.length,
        before, after,
        instanceCount: splatMesh.geometry.instanceCount,
        err,
        at: performance.now().toFixed(1),
    });
};
return "patched";
"""

PROBE2_JS = r"""
return new Promise(function (resolve) {
    const out = {};
    out.patchLogPre = window.__patchLog.slice();
    out.gatesPre = { sortRunning: viewer.sortRunning, splatRenderReady: viewer.splatRenderReady };
    out.drawRangePre = Object.assign({}, splatMesh.geometry.drawRange);

    viewer.runSplatSort(true, true).then(async function (sortRunning) {
        const t0 = performance.now();
        while (performance.now() - t0 < 3000) {
            if (!viewer.sortRunning) break;
            await new Promise(function (rr) { setTimeout(rr, 30); });
        }
        out.patchLogPost = window.__patchLog.slice();
        out.drawRangePost = Object.assign({}, splatMesh.geometry.drawRange);
        out.instanceCountPost = splatMesh.geometry.instanceCount;
        out.splatIndexAttrCount = splatMesh.geometry.attributes.splatIndex.count;

        // Try directly setting drawRange ourselves and rendering.
        splatMesh.geometry.setDrawRange(0, splatMesh.geometry.attributes.splatIndex.count);
        splatMesh.geometry.instanceCount = splatMesh.geometry.attributes.splatIndex.count;
        splatMesh.geometry.attributes.splatIndex.needsUpdate = true;
        viewer.renderer.info.reset();
        try { viewer.renderer.render(splatMesh, viewer.camera); } catch (e) { out.manualErr = e.message; }
        out.afterManualOverride = {
            renderInfo: JSON.parse(JSON.stringify(viewer.renderer.info.render)),
            drawRange: Object.assign({}, splatMesh.geometry.drawRange),
            instanceCount: splatMesh.geometry.instanceCount,
            matProgram: !!(splatMesh.material && splatMesh.material.program),
        };
        // Pixel check
        const c = document.getElementById('canvas');
        const gl = c.getContext('webgl2') || c.getContext('webgl');
        const px = new Uint8Array(c.width * c.height * 4);
        gl.readPixels(0, 0, c.width, c.height, gl.RGBA, gl.UNSIGNED_BYTE, px);
        let nb = 0, max = 0;
        for (let i = 0; i < px.length; i += 4) {
            const m = Math.max(px[i], px[i+1], px[i+2]);
            if (m > 30) nb++; if (m > max) max = m;
        }
        out.pixels = { nonBlack: nb, max };
        resolve(out);
    });
});
"""

def main():
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), _H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True,
            args=["--use-gl=swiftshader", "--ignore-gpu-blocklist"])
        ctx = browser.new_context(viewport={"width": 1024, "height": 768})
        page = ctx.new_page()
        page.on("console", lambda m: print(f"  {m.text}") if "frames" not in m.text else None)
        page.goto(f"http://127.0.0.1:{PORT}/viewer_gaussian.html", wait_until="load")
        page.wait_for_function("typeof window.__gs === 'object'")

        page.evaluate("""async () => {
            window._loaded = false; window._error = null;
            addEventListener('message', e => {
                if (e.data?.type === 'MESH_LOADED') window._loaded = true;
                if (e.data?.type === 'MESH_ERROR')  window._error  = e.data.error;
            });
            const r = await fetch('/test.ply'); const buf = await r.arrayBuffer();
            postMessage({ type:'LOAD_MESH_DATA', data: buf, filename:'t.ply', renderer:'webgl2' }, '*');
        }""")
        page.wait_for_function("window._loaded || window._error", timeout=180000)
        page.wait_for_timeout(1000)
        print("[harness] applying monkey-patch...")
        page.evaluate("(src) => window.__gs.run(src)", PATCH_JS)
        page.wait_for_timeout(500)
        print("[harness] running probe2...")
        result = page.evaluate("(src) => window.__gs.run(src)", PROBE2_JS)
        print(json.dumps(result, indent=2))
        page.screenshot(path="/tmp/viewer_probe2.png")
        browser.close()
    httpd.shutdown()

if __name__ == "__main__":
    main()
