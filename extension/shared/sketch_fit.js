// Sketchy çizimleri 640×480 tuvalin küçük bir bölgesinde durur. viewBox içeriğe çekilince
// hem oyun tuvalinde hem menü önizlemesinde ortada büyür. Quick Draw ve ikonlara dokunulmaz.
(() => {
  function markupFromSvgDataUrl(dataUrl) {
    const prefix = "data:image/svg+xml;base64,";
    if (!dataUrl.startsWith(prefix)) {
      return null;
    }
    const binary = atob(dataUrl.slice(prefix.length));
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return new TextDecoder().decode(bytes);
  }

  function dataUrlFromSvgMarkup(markup) {
    const bytes = new TextEncoder().encode(markup);
    let binary = "";
    for (const byte of bytes) {
      binary += String.fromCharCode(byte);
    }
    return `data:image/svg+xml;base64,${btoa(binary)}`;
  }

  function tightenSketchySvg(markup) {
    const parsed = new DOMParser().parseFromString(markup, "image/svg+xml");
    const svg = parsed.documentElement;
    if (
      svg.tagName.toLowerCase() !== "svg" ||
      svg.querySelector("parsererror") ||
      svg.getAttribute("viewBox") ||
      svg.getAttribute("width") !== "640" ||
      svg.getAttribute("height") !== "480"
    ) {
      return markup;
    }

    const probe = document.importNode(svg, true);
    probe.style.position = "absolute";
    probe.style.left = "-10000px";
    probe.style.top = "0";
    probe.style.visibility = "hidden";
    probe.style.pointerEvents = "none";
    document.documentElement.appendChild(probe);
    let box;
    try {
      box = probe.getBBox();
    } finally {
      probe.remove();
    }
    if (!box || box.width < 1 || box.height < 1) {
      return markup;
    }

    const pad = Math.max(box.width, box.height) * 0.08;
    const viewWidth = box.width + pad * 2;
    const viewHeight = box.height + pad * 2;
    svg.setAttribute("viewBox", `${box.x - pad} ${box.y - pad} ${viewWidth} ${viewHeight}`);
    svg.setAttribute("width", String(viewWidth));
    svg.setAttribute("height", String(viewHeight));
    return new XMLSerializer().serializeToString(svg);
  }

  function fitSketchyDrawing(imageDataUrl) {
    const markup = markupFromSvgDataUrl(imageDataUrl);
    if (!markup) {
      return imageDataUrl;
    }
    const tightened = tightenSketchySvg(markup);
    return tightened === markup ? imageDataUrl : dataUrlFromSvgMarkup(tightened);
  }

  globalThis.fitSketchyDrawing = fitSketchyDrawing;
})();
