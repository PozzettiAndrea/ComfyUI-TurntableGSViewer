// Sample the canvas back via gl.readPixels.
const c = document.getElementById('canvas');
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
return {
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
