// Force a full sort, wait for the worker to finish, then check drawRange
// and run one manual render call. Returns a Promise so page.evaluate awaits.
return new Promise((resolve) => {
    const out = {};
    const g  = splatMesh.geometry;
    out.before = {
        drawRange:     { start: g.drawRange.start, count: g.drawRange.count },
        instanceCount: g.instanceCount,
        sortRunning:   viewer.sortRunning,
        splatRenderCount:   viewer.splatRenderCount,
        lastSplatSortCount: viewer.lastSplatSortCount,
    };

    viewer.runSplatSort(true, true).then(async (sortRunning) => {
        out.runSplatSortReturned = sortRunning;
        const t0 = performance.now();
        while (performance.now() - t0 < 3000) {
            if (!viewer.sortRunning && g.drawRange.count > 0) break;
            await new Promise((rr) => setTimeout(rr, 30));
        }
        out.after = {
            drawRange:     { start: g.drawRange.start, count: g.drawRange.count },
            instanceCount: g.instanceCount,
            sortRunning:   viewer.sortRunning,
            splatRenderCount:   viewer.splatRenderCount,
            lastSplatSortCount: viewer.lastSplatSortCount,
            lastSortTime:       viewer.lastSortTime,
        };
        viewer.renderer.info.reset();
        try { viewer.renderer.render(splatMesh, viewer.camera); }
        catch (e) { out.renderErr = e.message; }
        out.renderInfo = JSON.parse(JSON.stringify(viewer.renderer.info.render));
        out.matProgram = !!(splatMesh.material && splatMesh.material.program);
        resolve(out);
    });
});
