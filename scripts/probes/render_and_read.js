// Render synchronously then read pixels in the same call, before any RAF
// clears the back buffer.
const out = {};
const g = splatMesh.geometry;
out.preDrawRange = { start: g.drawRange.start, count: g.drawRange.count };
out.preInstanceCount = g.instanceCount;

viewer.renderer.info.reset();
try { viewer.renderer.render(splatMesh, viewer.camera); }
catch (e) { out.renderErr = e.message; }
out.renderInfo = JSON.parse(JSON.stringify(viewer.renderer.info.render));

const c  = document.getElementById('canvas');
const gl = c.getContext('webgl2') || c.getContext('webgl');
const px = new Uint8Array(c.width * c.height * 4);
gl.readPixels(0, 0, c.width, c.height, gl.RGBA, gl.UNSIGNED_BYTE, px);
let nb = 0, max = 0, rSum = 0, gSum = 0, bSum = 0;
for (let i = 0; i < px.length; i += 4) {
    const r = px[i], gg = px[i+1], b = px[i+2];
    const m = Math.max(r, gg, b);
    if (m > 30) nb++;
    if (m > max) max = m;
    rSum += r; gSum += gg; bSum += b;
}
out.pixels = {
    wh: [c.width, c.height],
    nonBlackPx: nb,
    totalPx: px.length/4,
    max,
    avg: [
        +(rSum / (px.length/4)).toFixed(2),
        +(gSum / (px.length/4)).toFixed(2),
        +(bSum / (px.length/4)).toFixed(2),
    ],
};
out.matProgramAfter = !!(splatMesh.material && splatMesh.material.program);
return out;
