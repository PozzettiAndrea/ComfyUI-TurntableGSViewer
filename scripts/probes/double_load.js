// Trigger a SECOND LOAD_MESH_DATA (re-using the same PLY blob) and
// verify the viewer ends up with exactly one scene + a sensible splat
// count, not double the splats.
return new Promise(async (resolve) => {
    const out = {};
    const before = {
        splatCount: splatMesh.getSplatCount(),
        sceneCount: viewer.getSceneCount ? viewer.getSceneCount() : null,
    };
    out.before = before;

    // Fetch the PLY again from the in-page test endpoint and dispatch.
    const r = await fetch('/test.ply');
    const buf = await r.arrayBuffer();
    window._mesh_loaded = false; window._mesh_error = null;
    window.postMessage({
        type: 'LOAD_MESH_DATA',
        data: buf,
        filename: 't.ply',
        renderer: 'webgl2',
    }, '*');
    const t0 = performance.now();
    while (performance.now() - t0 < 60000) {
        if (window._mesh_loaded || window._mesh_error) break;
        await new Promise((rr) => setTimeout(rr, 100));
    }
    out.secondLoadError = window._mesh_error;
    // Give the post-load framing a moment to settle.
    await new Promise((rr) => setTimeout(rr, 1000));

    out.after = {
        splatCount: viewer.splatMesh && viewer.splatMesh.getSplatCount(),
        sceneCount: viewer.getSceneCount ? viewer.getSceneCount() : null,
        drawRangeCount: viewer.splatMesh && viewer.splatMesh.geometry.drawRange.count,
    };
    resolve(out);
});
