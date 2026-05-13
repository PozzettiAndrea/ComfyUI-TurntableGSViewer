#!/usr/bin/env python3
"""Load the viewer with a PLY then run a sequence of probe JS files against
it. Each probe file lives at scripts/probes/*.js and is executed inside the
__gs.run() sandbox with (adapter, viewer, splatMesh, THREE, GS) bound."""
import json, sys, pathlib, socketserver, threading
from http.server import SimpleHTTPRequestHandler
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
PROBES_DIR = HERE / "probes"
VIEWER_DIR = (HERE.parent / "web").resolve()
PLY_PATH = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(
    "/home/work/lito/ComfyUI/output/lito_output.ply"
)
PORT = 18437

# Comma-separated list of probe names (relative to scripts/probes, no extension).
# Defaults to: state, force_sort_and_render, state, pixels
PROBES = sys.argv[2].split(",") if len(sys.argv) > 2 else \
    ["state", "force_sort_and_render", "state", "pixels"]


class _H(SimpleHTTPRequestHandler):
    def translate_path(self, p):
        if p.split("?",1)[0] == "/test.ply": return str(PLY_PATH)
        return super().translate_path(p)
    def log_message(self, *a): pass
    def __init__(self, *a, **kw): super().__init__(*a, directory=str(VIEWER_DIR), **kw)


def main():
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), _H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True,
            args=["--use-gl=swiftshader", "--ignore-gpu-blocklist"])
        ctx = browser.new_context(viewport={"width": 1024, "height": 768})
        page = ctx.new_page()
        page.on("console", lambda m: print(f"  {m.text}") if "heartbeat" not in m.text else None)
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

        for probe_name in PROBES:
            probe_path = PROBES_DIR / f"{probe_name}.js"
            print(f"\n========== probe: {probe_name} ==========")
            js = probe_path.read_text()
            if probe_name in ("pixels", "screenshot"):
                result = page.evaluate(f"() => {{ {js} }}")
            else:
                result = page.evaluate("(src) => window.__gs.run(src)", js)
            if probe_name == "screenshot" and isinstance(result, dict) and "dataUrl" in result:
                import base64
                b64 = result["dataUrl"].split(",", 1)[1]
                out_png = f"/tmp/viewer_screenshot.png"
                with open(out_png, "wb") as f:
                    f.write(base64.b64decode(b64))
                print(f"  saved {out_png} ({len(b64)*3//4} bytes)")
            else:
                print(json.dumps(result, indent=2))

        browser.close()
    httpd.shutdown()

if __name__ == "__main__":
    main()
