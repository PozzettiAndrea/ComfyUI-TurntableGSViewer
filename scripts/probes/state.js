// State probe for the Spark-based adapter. Pure read; no side effects.
return {
    adapterReady: !!adapter,
    adapterKind:  adapter && adapter.kind && adapter.kind(),
    splatCount:   splatMesh?.numSplats ?? splatMesh?.getSplatCount?.() ?? 0,
    cameraPos:    adapter ? adapter.getCameraPosition() : null,
    cameraTarget: adapter ? adapter.getCameraTarget() : null,
    fov:          adapter && adapter.camera ? adapter.camera.fov : null,
    frames:       adapter && adapter._frameCount,
    sceneChildren: scene ? scene.children.map(c => ({ type: c.type, visible: c.visible })) : null,
};
