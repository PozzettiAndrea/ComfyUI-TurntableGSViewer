#!/usr/bin/env python3
"""Probe the loaded viewer: gating flags, sort state, splat tree, geometry, and
force-render. Pass the probe JS as a JSON-encoded string to avoid wrestling
with shell + JS-template-literal escaping."""
import json
import sys
import time
import pathlib
import socketserver
import threading
from http.server import SimpleHTTPRequestHandler

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
VIEWER_DIR = (HERE.parent / "web").resolve()
PLY_PATH = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(
    "/home/work/lito/ComfyUI/output/lito_output.ply"
)
PORT = 18435


class _H(SimpleHTTPRequestHandler):
    def translate_path(self, p):
        clean = p.split("?", 1)[0]
        if clean == "/test.ply":
            return str(PLY_PATH)
        return super().translate_path(p)
    def log_message(self, *a): pass
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(VIEWER_DIR), **kw)


PROBE_JS = r"""
const out = {};
const r = viewer.renderer;

// Renderer baseline
out.rendererInfo  = JSON.parse(JSON.stringify(r.info));
out.renderTarget  = !!r.getRenderTarget();
out.viewport      = r.getViewport(new THREE.Vector4()).toArray();
out.size          = r.getSize(new THREE.Vector2()).toArray();
out.dprSize       = r.getDrawingBufferSize(new THREE.Vector2()).toArray();
out.autoClear     = r.autoClear;

// Gating flags
out.gates = {
    initialized: viewer.initialized,
    splatRenderReady: viewer.splatRenderReady,
    disposing: viewer.disposing,
    disposed: viewer.disposed,
    sortRunning: viewer.sortRunning,
    selfDrivenModeRunning: viewer.selfDrivenModeRunning,
};

// Camera
out.camera = {
    pos: viewer.camera.position.toArray(),
    quat: viewer.camera.quaternion.toArray(),
    near: viewer.camera.near, far: viewer.camera.far,
    fov: viewer.camera.fov, aspect: viewer.camera.aspect,
};

// splatMesh geometry
const g = splatMesh.geometry;
out.geom = {
    type: splatMesh.type,
    geomType: g.type,
    drawRangeBefore: { start: g.drawRange.start, count: g.drawRange.count },
    instanceCountBefore: g.instanceCount,
    visible: splatMesh.visible,
    inScene: !!splatMesh.parent,
    frustumCulled: splatMesh.frustumCulled,
};
out.geom.attrs = {};
for (const k of Object.keys(g.attributes || {})) {
    const a = g.attributes[k];
    out.geom.attrs[k] = { itemSize: a.itemSize, count: a.count, instanced: !!a.isInstancedBufferAttribute };
}

// Sort state
out.sortState = {
    splatRenderCount: viewer.splatRenderCount,
    lastSplatSortCount: viewer.lastSplatSortCount,
    lastSortTime: viewer.lastSortTime,
    gpuAcceleratedSort: viewer.gpuAcceleratedSort,
};

// Splat tree
try {
    const tree = splatMesh.getSplatTree && splatMesh.getSplatTree();
    if (!tree) {
        out.splatTree = "NULL (sorter falls back to whole-buffer path)";
    } else {
        out.splatTree = {
            subTrees: (tree.subTrees || []).map(function (st, i) {
                const nodes = st.nodesWithIndexes || [];
                const sample = nodes[0] ? {
                    center: nodes[0].center && nodes[0].center.toArray(),
                    min: nodes[0].min && nodes[0].min.toArray(),
                    max: nodes[0].max && nodes[0].max.toArray(),
                    indexesLen: nodes[0].data && nodes[0].data.indexes && nodes[0].data.indexes.length,
                } : null;
                let withIdx = 0, totalIdx = 0;
                for (const n of nodes) {
                    if (n.data && n.data.indexes) { withIdx++; totalIdx += n.data.indexes.length; }
                }
                return { subTreeIdx: i, nodeCount: nodes.length, nodesWithIndexes: withIdx, totalIndexes: totalIdx, sample };
            }),
        };
    }
} catch (e) {
    out.splatTreeErr = e.message;
}

// Probe a known-good draw (proves the renderer/canvas pipeline is healthy)
try {
    const probeGeo = new THREE.PlaneGeometry(2, 2);
    const probeMat = new THREE.MeshBasicMaterial({ color: 0xff0000 });
    const probeMesh = new THREE.Mesh(probeGeo, probeMat);
    const probeScene = new THREE.Scene();
    probeScene.add(probeMesh);
    const probeCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10);
    probeCam.position.z = 1;
    r.info.reset();
    r.render(probeScene, probeCam);
    out.probeRender = JSON.parse(JSON.stringify(r.info.render));
} catch (e) { out.probeRenderErr = e.message; }

// Force a sort and wait for the worker to finish
return new Promise(function (resolve) {
    viewer.runSplatSort(true, true).then(async function (sortRunning) {
        out.runSplatSortReturned = sortRunning;
        const t0 = performance.now();
        while (performance.now() - t0 < 3000) {
            if (!viewer.sortRunning && g.drawRange.count > 0) break;
            await new Promise(function (rr) { setTimeout(rr, 50); });
        }
        out.afterForcedSort = {
            splatRenderCount: viewer.splatRenderCount,
            lastSplatSortCount: viewer.lastSplatSortCount,
            lastSortTime: viewer.lastSortTime,
            sortRunning: viewer.sortRunning,
            drawRangeAfter: { start: g.drawRange.start, count: g.drawRange.count },
            instanceCountAfter: g.instanceCount,
        };

        // Force one render now that the sort should have populated drawRange
        r.info.reset();
        try { r.render(splatMesh, viewer.camera); } catch (e) { out.afterRenderErr = e.message; }
        out.afterForcedSortRender = JSON.parse(JSON.stringify(r.info.render));
        out.matProgramFinal = !!(splatMesh.material && splatMesh.material.program);
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
        page.wait_for_timeout(1500)

        # Pass probe JS as a function arg → no template-literal headaches.
        probe = page.evaluate("(src) => window.__gs.run(src)", PROBE_JS)
        print("[probe]\n" + json.dumps(probe, indent=2))

        hist = page.evaluate("""() => {
            const c = document.getElementById('canvas');
            const gl = c.getContext('webgl2') || c.getContext('webgl');
            const pixels = new Uint8Array(c.width * c.height * 4);
            gl.readPixels(0, 0, c.width, c.height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
            let nb = 0, max = 0;
            for (let i = 0; i < pixels.length; i += 4) {
                const m = Math.max(pixels[i], pixels[i+1], pixels[i+2]);
                if (m > 30) nb++; if (m > max) max = m;
            }
            return { nonBlackPx: nb, totalPx: pixels.length/4, max };
        }""")
        print("[hist after manual render]:", hist)

        page.screenshot(path="/tmp/viewer_probe.png")
        print("[shot] /tmp/viewer_probe.png")
        browser.close()
    httpd.shutdown()

if __name__ == "__main__":
    main()
