// Capture the canvas as a base64 PNG. Returns { dataUrl } for the caller
// to decode + save outside the page. Avoids Playwright's page.screenshot()
// which seems to hang on this scene.
const c = document.getElementById('canvas');
return { dataUrl: c.toDataURL('image/png') };
