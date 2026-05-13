// Read viewer + splatMesh + renderer state. Pure data dump, no side-effects
// (no manual render, no forced sort).
//
// Returned as a JSON-friendly object. window.__gs.run() calls this with
// (adapter, viewer, splatMesh, THREE, GS) bound.
const out = {};
const r = viewer.renderer;

out.gates = {
    initialized: viewer.initialized,
    splatRenderReady: viewer.splatRenderReady,
    disposing: viewer.disposing,
    disposed: viewer.disposed,
    sortRunning: viewer.sortRunning,
    selfDrivenModeRunning: viewer.selfDrivenModeRunning,
    splatRenderCount: viewer.splatRenderCount,
    lastSplatSortCount: viewer.lastSplatSortCount,
    lastSortTime: viewer.lastSortTime,
    gpuAcceleratedSort: viewer.gpuAcceleratedSort,
};

out.rendererInfo = JSON.parse(JSON.stringify(r.info));
out.size         = r.getSize(new THREE.Vector2()).toArray();
out.dprSize      = r.getDrawingBufferSize(new THREE.Vector2()).toArray();
out.autoClear    = r.autoClear;
out.renderTarget = !!r.getRenderTarget();

out.camera = {
    pos: viewer.camera.position.toArray(),
    quat: viewer.camera.quaternion.toArray(),
    near: viewer.camera.near, far: viewer.camera.far,
    fov: viewer.camera.fov, aspect: viewer.camera.aspect,
};

const g = splatMesh.geometry;
out.geom = {
    type: splatMesh.type,
    geomType: g.type,
    drawRange: { start: g.drawRange.start, count: g.drawRange.count },
    instanceCount: g.instanceCount,
    visible: splatMesh.visible,
    inScene: !!splatMesh.parent,
    frustumCulled: splatMesh.frustumCulled,
    attrs: {},
};
for (const k of Object.keys(g.attributes || {})) {
    const a = g.attributes[k];
    out.geom.attrs[k] = {
        itemSize: a.itemSize,
        count:    a.count,
        instanced: !!a.isInstancedBufferAttribute,
    };
}

// Material
const mat = splatMesh.material;
out.material = {
    type: mat && mat.type,
    visible: mat && mat.visible,
    transparent: mat && mat.transparent,
    program: !!(mat && mat.program),
    uniformsKeys: mat && mat.uniforms ? Object.keys(mat.uniforms) : null,
};

return out;
