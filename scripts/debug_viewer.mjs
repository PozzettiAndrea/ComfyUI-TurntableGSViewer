#!/usr/bin/env node
// Playwright harness: load viewer_gaussian.html in headless Chromium, push the
// user's PLY through LOAD_MESH_DATA, then introspect the rendered canvas.
//
// Usage:  node debug_viewer.mjs [path/to/file.ply]

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname  = path.dirname(__filename);
const VIEWER_DIR = path.resolve(__dirname, '..', 'web');
const PLY_PATH   = process.argv[2] || '/home/work/lito/ComfyUI/output/lito_output.ply';
const PORT       = 18432;

const MIME = {
    '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css',
    '.ply': 'application/octet-stream',
};

function startStaticServer() {
    return new Promise((resolve) => {
        const server = http.createServer((req, res) => {
            const u = decodeURIComponent(req.url.split('?')[0]);
            let filePath;
            if (u === '/test.ply') filePath = PLY_PATH;
            else {
                filePath = path.normalize(path.join(VIEWER_DIR, u));
                if (!filePath.startsWith(VIEWER_DIR)) { res.writeHead(403); res.end(); return; }
            }
            fs.stat(filePath, (err, st) => {
                if (err || !st.isFile()) { res.writeHead(404); res.end('not found'); return; }
                const ext = path.extname(filePath).toLowerCase();
                res.writeHead(200, {
                    'Content-Type': MIME[ext] || 'application/octet-stream',
                    'Content-Length': st.size,
                    'Cache-Control': 'no-cache',
                });
                fs.createReadStream(filePath).pipe(res);
            });
        });
        server.listen(PORT, '127.0.0.1', () => {
            const a = server.address();
            console.log(`[harness] static server: http://127.0.0.1:${a.port}/`);
            resolve(server);
        });
    });
}

async function main() {
    const playwrightPath = process.env.PLAYWRIGHT_NODE
        || '/home/andrej/.local/share/uv/python/cpython-3.13.7-linux-x86_64-gnu/lib/python3.13/site-packages/playwright/driver/package';
    // Resolve playwright via the python install's node bundle.
    const { chromium } = await import(`${playwrightPath}/lib/cjs/playwright.js`).catch(() => import('playwright'));

    const server = await startStaticServer();
    const browser = await chromium.launch({
        headless: true,
        args: ['--use-gl=swiftshader', '--ignore-gpu-blocklist', '--enable-webgl'],
    });
    const ctx = await browser.newContext({ viewport: { width: 1024, height: 768 } });
    const page = await ctx.newPage();

    page.on('console', m => {
        const t = m.type();
        if (t === 'log') console.log(`  ${m.text()}`);
        else            console.log(`  [${t}] ${m.text()}`);
    });
    page.on('pageerror', e => console.log(`  [pageerror] ${e.message}`));

    console.log('[harness] navigating to viewer...');
    await page.goto(`http://127.0.0.1:${PORT}/viewer_gaussian.html`, { waitUntil: 'load' });
    await page.waitForFunction(() => typeof window.__gs === 'object');

    console.log(`[harness] fetching PLY: ${PLY_PATH}`);
    const t0 = Date.now();
    const result = await page.evaluate(async () => {
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
        return { bytes: buf.byteLength };
    });
    console.log(`[harness] handed off ${(result.bytes / 1e6).toFixed(1)} MB to the iframe`);

    console.log('[harness] waiting for MESH_LOADED or MESH_ERROR...');
    try {
        await page.waitForFunction(() => window._mesh_loaded || window._mesh_error,
                                   { timeout: 120000 });
    } catch (e) {
        console.log('[harness] TIMED OUT waiting for load:', e.message);
    }
    const err = await page.evaluate(() => window._mesh_error);
    if (err) console.log(`[harness] viewer reported MESH_ERROR: ${err}`);
    console.log(`[harness] load roundtrip: ${((Date.now()-t0)/1000).toFixed(1)} s`);

    // Let the renderer pump frames.
    await new Promise(r => setTimeout(r, 2500));

    const state = await page.evaluate(() => window.__gs.state());
    console.log('[harness] viewer state:', JSON.stringify(state, null, 2));

    // ---- Probe A: pixel histogram via gl.readPixels --------------
    const px = await page.evaluate(() => {
        const c = document.getElementById('canvas');
        const gl = c.getContext('webgl2') || c.getContext('webgl');
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
            nonBlackPct: (nonBlack / total * 100).toFixed(2),
            avg: [rSum / total, gSum / total, bSum / total, aSum / total].map(v => +v.toFixed(2)),
            max,
            ctxLost: gl.isContextLost(),
            vendor: gl.getParameter(gl.VENDOR),
            renderer: gl.getParameter(gl.RENDERER),
        };
    });
    console.log('[harness] pixel histogram:', JSON.stringify(px, null, 2));

    // ---- Probe B: splat data sanity ------------------------------
    const splatSample = await page.evaluate(() => {
        return window.__gs.run(`
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
                try { splatMesh.getSplatColor(i, c); col = [c[0], c[1], c[2], c[3]]; } catch (e) { err = (err ? err + '; ' : '') + 'color: ' + e.message; }
                return { i, pos, col, err };
            });
            // Try getSplatScale & getSplatRotation if available
            try { out.hasGetSplatScale = !!splatMesh.getSplatScale; } catch (e) {}
            // Inspect splatBuffer for SH degree
            try {
                const sb = splatMesh.splatBuffer || splatMesh.splatBuffers && splatMesh.splatBuffers[0];
                if (sb) {
                    out.splatBufferKeys = Object.keys(sb).filter(k => !k.startsWith('_')).slice(0, 40);
                    out.minSHDegree = sb.minSphericalHarmonicsDegree;
                    out.maxSHDegree = sb.maxSphericalHarmonicsDegree;
                    out.outSHDegree = sb.outSphericalHarmonicsDegree;
                    out.sceneCount  = sb.getSceneCount && sb.getSceneCount();
                    out.splatCount  = sb.getSplatCount && sb.getSplatCount();
                }
            } catch (e) { out.splatBufferErr = e.message; }
            // Check material
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
            // Mesh in scene?
            try {
                out.meshVisible = splatMesh.visible;
                out.meshInScene = !!splatMesh.parent;
                out.meshParentType = splatMesh.parent && splatMesh.parent.type;
                out.meshPos = [splatMesh.position.x, splatMesh.position.y, splatMesh.position.z];
                const bb = splatMesh.geometry && splatMesh.geometry.boundingBox;
                if (bb) out.geomBB = { min: bb.min.toArray(), max: bb.max.toArray() };
                else out.geomBB = null;
            } catch (e) { out.meshErr = e.message; }
            return out;
        `);
    });
    console.log('[harness] splat data probe:', JSON.stringify(splatSample, null, 2));

    // ---- Probe C: scene walk ------------------------------------
    const sceneInfo = await page.evaluate(() => {
        return window.__gs.run(`
            const scene = viewer && viewer.threeScene;
            if (!scene) return { error: "no scene" };
            const out = { childCount: scene.children.length, children: [] };
            scene.traverse((o) => {
                out.children.push({
                    type: o.type, name: o.name, visible: o.visible,
                    pos: [o.position.x, o.position.y, o.position.z],
                });
            });
            return out;
        `);
    });
    console.log('[harness] three.js scene:', JSON.stringify(sceneInfo, null, 2));

    const shotPath = '/tmp/viewer_debug.png';
    await page.screenshot({ path: shotPath, fullPage: false });
    console.log(`[harness] screenshot saved: ${shotPath}`);

    await browser.close();
    server.close();
}

main().catch(e => { console.error('[harness] FATAL:', e); process.exit(1); });
