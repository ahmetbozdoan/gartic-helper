(() => {
  const helper = globalThis.GarticHelper;

  const OVERLAY_STYLES = `
    :host {
      position: absolute;
      inset: 0;
      pointer-events: none;
      /* Line-art'ın beyaz zemini çizimi örtmesin */
      mix-blend-mode: multiply;
      z-index: 50;
    }
    img {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }
  `;

  let overlayHost = null;
  let overlayImage = null;

  function show(imageDataUrl, opacity) {
    const drawingContainer = document.querySelector(helper.SELECTORS.drawingContainer);
    if (!drawingContainer) {
      return false;
    }
    if (getComputedStyle(drawingContainer).position === "static") {
      drawingContainer.style.position = "relative";
    }

    if (!overlayHost) {
      const { hostElement, shadowRoot } = helper.createShadowHost(OVERLAY_STYLES);
      overlayImage = document.createElement("img");
      overlayImage.alt = "";
      overlayImage.draggable = false;
      shadowRoot.appendChild(overlayImage);
      overlayHost = hostElement;
    }
    if (overlayHost.parentElement !== drawingContainer) {
      drawingContainer.appendChild(overlayHost);
    }
    overlayImage.src = globalThis.fitSketchyDrawing(imageDataUrl);
    setOpacity(opacity);
    return true;
  }

  function setOpacity(opacity) {
    if (overlayImage) {
      overlayImage.style.opacity = String(opacity);
    }
  }

  function hide() {
    overlayHost?.remove();
    overlayHost = null;
    overlayImage = null;
  }

  function isVisible() {
    return overlayHost?.isConnected ?? false;
  }

  helper.guideOverlay = { show, setOpacity, hide, isVisible };
})();
