/**
 * ComfyUI-TurntableGSViewer - Gaussian Splat Preview Widget
 * Interactive 3D Gaussian Splatting viewer using gsplat.js
 */

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

// Auto-detect extension folder name (so this copy doesn't collide with upstream comfyui-PlyPreview).
const EXTENSION_FOLDER = (() => {
    const url = import.meta.url;
    const match = url.match(/\/extensions\/([^/]+)\//);
    return match ? match[1] : "ComfyUI-TurntableGSViewer";
})();

console.log("[TurntableGSViewer] Loading extension...");

app.registerExtension({
    name: "turntablegsviewer.previewgaussians",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // Auto-refresh PLY dropdown list for the file selector node
        if (nodeData.name === "PlyPreviewLoadGaussianPLYEnhance") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function() {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

                const widget = (this.widgets || []).find(w => w.name === "ply_file");

                const refreshList = async () => {
                    try {
                        const resp = await api.fetchApi("/plypreview/files");
                        const json = await resp.json();
                        const files = Array.isArray(json.files) && json.files.length > 0 ? json.files : ["No PLY files found"];
                        if (widget) {
                            // Update dropdown choices and keep current selection if still present
                            widget.options = { ...(widget.options || {}), values: files };
                            if (!files.includes(widget.value)) {
                                widget.value = files[0];
                                widget.callback?.(widget.value);
                            }
                            // Force UI redraw
                            widget.computeSize?.();
                            this.setDirtyCanvas(true);
                            app.graph.setDirtyCanvas(true, true);
                        }
                    } catch (e) {
                        console.warn("[TurntableGSViewer] Failed to refresh PLY list", e);
                    }
                };

                this.refreshPlyList = refreshList;
                refreshList();

                // Hint label: user must right-click "Reload Node" to refresh PLY list
                const hintEl = document.createElement("div");
                hintEl.style.cssText = "font-size:10px;color:#888;text-align:center;padding:4px 8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
                hintEl.textContent = "Right-click → Refresh Node to load new PLY files";
                this.addDOMWidget("ply_hint", "PLY_HINT", hintEl, {
                    serialize: false,
                    hideOnZoom: false,
                });

                return r;
            };
        }

        if (nodeData.name === "PreviewGaussians") {
            console.log("[TurntableGSViewer] Registering Preview Gaussians node");

            // After ComfyUI applies serialized widgets_values, reset any numeric
            // widget whose value is a string. Earlier versions of this code
            // persisted camera state into widgets_values, shifting fov/width/
            // height by one slot on reload. onConfigure runs AFTER configure()
            // has stamped the saved (possibly bad) values onto the widgets,
            // so this is where the migration has to live — onNodeCreated runs
            // before configure() and would only see fresh defaults.
            const _origOnConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function(info) {
                const r = _origOnConfigure ? _origOnConfigure.apply(this, arguments) : undefined;
                for (const w of (this.widgets || [])) {
                    if ((w.type === "number" || w.type === "INT" || w.type === "FLOAT")
                        && typeof w.value === "string") {
                        const def = w.options?.default;
                        console.warn("[TurntableGSViewer] resetting corrupted widget",
                                     w.name, "(was string) ->", def);
                        w.value = (def !== undefined) ? def : 0;
                    }
                    // Also clamp out-of-range numerics (e.g. the shifted
                    // fov_degrees=512 from a saved-then-shifted workflow).
                    if (typeof w.value === "number" && w.options) {
                        const { min, max, default: def } = w.options;
                        if ((typeof min === "number" && w.value < min) ||
                            (typeof max === "number" && w.value > max)) {
                            console.warn("[TurntableGSViewer] resetting out-of-range widget",
                                         w.name, w.value, "->", def);
                            w.value = (def !== undefined) ? def : (min ?? 0);
                        }
                    }
                }
                return r;
            };

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function() {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

                // Create container for viewer + info panel
                const container = document.createElement("div");
                container.style.width = "100%";
                container.style.height = "100%";
                container.style.display = "flex";
                container.style.flexDirection = "column";
                container.style.backgroundColor = "#1a1a1a";
                container.style.overflow = "hidden";

                // Create iframe for gsplat.js viewer
                const iframe = document.createElement("iframe");
                iframe.style.width = "100%";
                iframe.style.flex = "1 1 0";
                iframe.style.minHeight = "0";
                iframe.style.border = "none";
                iframe.style.backgroundColor = "#1a1a1a";

                // Point to gsplat.js HTML viewer (with cache buster)
                iframe.src = `/extensions/${EXTENSION_FOLDER}/viewer_gaussian.html?v=` + Date.now();

                // Create info panel
                const infoPanel = document.createElement("div");
                infoPanel.style.backgroundColor = "#1a1a1a";
                infoPanel.style.borderTop = "1px solid #444";
                infoPanel.style.padding = "6px 12px";
                infoPanel.style.fontSize = "10px";
                infoPanel.style.fontFamily = "monospace";
                infoPanel.style.color = "#ccc";
                infoPanel.style.lineHeight = "1.3";
                infoPanel.style.flexShrink = "0";
                infoPanel.style.overflow = "hidden";
                infoPanel.innerHTML = '<span style="color: #888;">Gaussian splat info will appear here after execution</span>';

                // Add iframe and info panel to container
                container.appendChild(iframe);
                container.appendChild(infoPanel);

                // --- Persistent camera-state plumbing ---------------------
                // Mirrors ComfyUI's built-in Load3D widget: state lives on
                // node.properties["Camera Config"] (named dict), NOT inside
                // widgets_values (positional). Putting the JSON string into
                // widgets_values shifts the standard fov/width/height widgets
                // by one slot on reload and breaks prompt validation.
                let pendingRestoreJSON = "";
                const sendRestore = () => {
                    if (!pendingRestoreJSON || !iframe.contentWindow) return;
                    try {
                        const state = JSON.parse(pendingRestoreJSON);
                        iframe.contentWindow.postMessage(
                            { type: "RESTORE_CAMERA_STATE", state }, "*",
                        );
                    } catch (e) {
                        console.warn("[TurntableGSViewer] bad saved camera state:", e);
                    }
                };

                // Seed pendingRestoreJSON from node.properties (Load3D pattern)
                // if the workflow JSON had a saved pose.
                const savedCfg = this.properties && this.properties["Camera Config"];
                if (savedCfg && typeof savedCfg.state === "string") {
                    pendingRestoreJSON = savedCfg.state;
                }

                // Iframe-display widget. serialize: false → never lands in
                // widgets_values; we own persistence via node.properties.
                const widget = this.addDOMWidget(
                    "preview_gaussian", "GAUSSIAN_PREVIEW", container,
                    { serialize: false },
                );

                // Store reference to node for dynamic resizing
                const node = this;
                let currentNodeSize = [512, 580];

                widget.computeSize = () => currentNodeSize;

                // Store references
                this.gaussianViewerIframe = iframe;
                this.gaussianInfoPanel = infoPanel;

                // Function to resize node dynamically
                this.resizeToAspectRatio = function(imageWidth, imageHeight) {
                    const aspectRatio = imageWidth / imageHeight;
                    const nodeWidth = 512;
                    const viewerHeight = Math.round(nodeWidth / aspectRatio);
                    const nodeHeight = viewerHeight + 60;  // Add space for info panel

                    currentNodeSize = [nodeWidth, nodeHeight];
                    node.setSize(currentNodeSize);
                    node.setDirtyCanvas(true, true);
                    app.graph.setDirtyCanvas(true, true);

                    console.log("[TurntableGSViewer] Resized node to:", nodeWidth, "x", nodeHeight, "(aspect ratio:", aspectRatio.toFixed(2), ")");
                };

                // Track iframe load state
                let iframeLoaded = false;
                iframe.addEventListener('load', () => {
                    iframeLoaded = true;
                    // Push any pending saved camera state now that the iframe is alive
                    // (e.g. on workflow reload before the node has been re-queued).
                    sendRestore();
                });

                // Listen for messages from iframe
                window.addEventListener('message', async (event) => {
                    // Only react to messages from OUR iframe — otherwise a
                    // second PreviewGaussians node's iframe would stomp this
                    // node's state.
                    if (event.source !== iframe.contentWindow) return;

                    // Camera-state pushes from iframe → persist on
                    // node.properties["Camera Config"] (Load3D pattern).
                    if (event.data?.type === "CAMERA_STATE" && event.data.state) {
                        const s = event.data.state;
                        node.properties = node.properties || {};
                        const cfg = node.properties["Camera Config"] || {};
                        cfg.cameraType = cfg.cameraType || "perspective";
                        cfg.fov = (typeof s.fov === "number") ? s.fov : (cfg.fov ?? 50);
                        cfg.state = JSON.stringify(s);
                        node.properties["Camera Config"] = cfg;
                        return;
                    }
                    // Iframe just finished a PLY load → if we have a saved
                    // pose, replay it. The iframe's loadPLYFromData already
                    // frames on bounds first, so this restore wins.
                    if (event.data?.type === "MESH_LOADED") {
                        sendRestore();
                    }
                    // Handle screenshot messages
                    if (event.data.type === 'SCREENSHOT' && event.data.image) {
                        try {
                            // Convert base64 data URL to blob
                            const base64Data = event.data.image.split(',')[1];
                            const byteString = atob(base64Data);
                            const arrayBuffer = new ArrayBuffer(byteString.length);
                            const uint8Array = new Uint8Array(arrayBuffer);

                            for (let i = 0; i < byteString.length; i++) {
                                uint8Array[i] = byteString.charCodeAt(i);
                            }

                            const blob = new Blob([uint8Array], { type: 'image/png' });

                            // Generate filename with timestamp
                            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
                            const filename = `gaussian-screenshot-${timestamp}.png`;

                            // Create FormData for upload
                            const formData = new FormData();
                            formData.append('image', blob, filename);
                            formData.append('type', 'output');
                            formData.append('subfolder', '');

                            // Upload to ComfyUI backend
                            const response = await fetch('/upload/image', {
                                method: 'POST',
                                body: formData
                            });

                            if (response.ok) {
                                const result = await response.json();
                                console.log('[TurntableGSViewer] Screenshot saved:', result.name);
                            } else {
                                throw new Error(`Upload failed: ${response.status}`);
                            }

                        } catch (error) {
                            console.error('[TurntableGSViewer] Error saving screenshot:', error);
                        }
                    }
                    // Handle error messages from iframe
                    else if (event.data.type === 'MESH_ERROR' && event.data.error) {
                        console.error('[TurntableGSViewer] Error from viewer:', event.data.error);
                        if (infoPanel) {
                            infoPanel.innerHTML = `<div style="color: #ff6b6b;">Error: ${event.data.error}</div>`;
                        }
                    }
                });

                // Set initial node size
                this.setSize([512, 580]);

                // Handle execution
                const onExecuted = this.onExecuted;
                this.onExecuted = function(message) {
                    console.log("[TurntableGSViewer] onExecuted called with:", message);
                    onExecuted?.apply(this, arguments);

                    // Check for errors
                    if (message?.error && message.error[0]) {
                        infoPanel.innerHTML = `<div style="color: #ff6b6b;">Error: ${message.error[0]}</div>`;
                        return;
                    }

                    // The message IS the UI data (not message.ui)
                    if (message?.ply_file && message.ply_file[0]) {
                        const filename = message.ply_file[0];
                        const displayName = message.filename?.[0] || filename;
                        const fileSizeMb = message.file_size_mb?.[0] || 'N/A';

                        // Extract camera parameters if provided
                        const extrinsics = message.extrinsics?.[0] || null;
                        const intrinsics = message.intrinsics?.[0] || null;

                        // Resize node to match image aspect ratio from intrinsics
                        if (intrinsics && intrinsics[0] && intrinsics[1]) {
                            const imageWidth = intrinsics[0][2] * 2;   // cx * 2
                            const imageHeight = intrinsics[1][2] * 2;  // cy * 2
                            this.resizeToAspectRatio(imageWidth, imageHeight);
                        }

                        // Update info panel
                        infoPanel.innerHTML = `
                            <div style="display: grid; grid-template-columns: auto 1fr; gap: 2px 8px;">
                                <span style="color: #888;">File:</span>
                                <span style="color: #6cc;">${displayName}</span>
                                <span style="color: #888;">Size:</span>
                                <span>${fileSizeMb} MB</span>
                            </div>
                        `;

                        // ComfyUI serves output files via /view API endpoint
                        const filepath = `/view?filename=${encodeURIComponent(filename)}&type=output&subfolder=`;

                        // Function to fetch and send data to iframe
                        const fetchAndSend = async () => {
                            if (!iframe.contentWindow) {
                                console.error("[TurntableGSViewer] Iframe contentWindow not available");
                                return;
                            }

                            try {
                                // Fetch the PLY file from parent context (authenticated)
                                console.log("[TurntableGSViewer] Fetching PLY file:", filepath);
                                const response = await fetch(filepath);
                                if (!response.ok) {
                                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                                }
                                const arrayBuffer = await response.arrayBuffer();
                                console.log("[TurntableGSViewer] Fetched PLY file, size:", arrayBuffer.byteLength);

                                // Send the data to iframe with camera parameters
                                iframe.contentWindow.postMessage({
                                    type: "LOAD_MESH_DATA",
                                    data: arrayBuffer,
                                    filename: filename,
                                    extrinsics: extrinsics,
                                    intrinsics: intrinsics,
                                    timestamp: Date.now()
                                }, "*", [arrayBuffer]);
                            } catch (error) {
                                console.error("[TurntableGSViewer] Error fetching PLY:", error);
                                infoPanel.innerHTML = `<div style="color: #ff6b6b;">Error loading PLY: ${error.message}</div>`;
                            }
                        };

                        // Fetch and send when iframe is ready
                        if (iframeLoaded) {
                            fetchAndSend();
                        } else {
                            setTimeout(fetchAndSend, 500);
                        }
                    }
                };

                return r;
            };
        }
    }
});
