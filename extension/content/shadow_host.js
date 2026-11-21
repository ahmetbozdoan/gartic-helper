(() => {
  const helper = globalThis.GarticHelper;

  // Reklam engelleyicilerin kozmetik filtreleri id/sınıf adlarına göre eşleşir; her yüklemede rastgele
  // üretilen etiket adı ve kapalı shadow DOM sayesinde arayüz bu filtrelere takılmaz.
  const HOST_TAG_NAME = `x-${Math.random().toString(36).slice(2, 10).replace(/[^a-z0-9]/g, "a")}`;

  /** Stilleri ve içeriği dış sayfadan yalıtılmış bir kapsayıcı oluşturur (DOM'a eklemez). */
  function createShadowHost(cssText) {
    const hostElement = document.createElement(HOST_TAG_NAME);
    const shadowRoot = hostElement.attachShadow({ mode: "closed" });
    const styleElement = document.createElement("style");
    styleElement.textContent = cssText;
    shadowRoot.appendChild(styleElement);
    return { hostElement, shadowRoot };
  }

  helper.createShadowHost = createShadowHost;
})();
