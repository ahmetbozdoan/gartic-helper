(() => {
  const helper = globalThis.GarticHelper;
  const PANEL_STYLES = `
    :host {
      all: initial;
      position: fixed;
      top: 80px;
      right: 16px;
      width: 300px;
      z-index: 2147483647;
    }
    .gh-panel {
      font: 13px/1.4 "Segoe UI", Arial, sans-serif;
      color: #1b2a4a;
      background: #ffffff;
      border: 2px solid #1a56db;
      border-radius: 10px;
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
      user-select: none;
    }
    .gh-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 10px;
      background: #1a56db;
      color: #ffffff;
      border-radius: 7px 7px 0 0;
      cursor: move;
    }
    .gh-title {
      font-weight: 700;
    }
    .gh-icon-button {
      border: none;
      background: transparent;
      color: inherit;
      font-size: 16px;
      cursor: pointer;
    }
    .gh-panel.gh-collapsed .gh-body {
      display: none;
    }
    .gh-body {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 10px;
    }
    .gh-status[data-kind="error"] {
      color: #c81e1e;
    }
    .gh-status[data-kind="busy"] {
      color: #9a6700;
    }
    .gh-drawing-word {
      font-weight: 700;
      font-size: 14px;
    }
    .gh-hint {
      font-family: Consolas, monospace;
      letter-spacing: 1px;
    }
    .gh-panel[data-mode="draw"] [data-section="guess"],
    .gh-panel[data-mode="guess"] [data-section="guide"] {
      display: none;
    }
    section {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .gh-candidates {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }
    .gh-candidate {
      padding: 3px 8px;
      border: 1px solid #1a56db;
      border-radius: 12px;
      background: #e8f0fe;
      color: #1a56db;
      cursor: pointer;
    }
    .gh-candidate:hover {
      background: #1a56db;
      color: #ffffff;
    }
    .gh-row {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    input[type="range"] {
      flex: 1;
      min-width: 0;
    }
    .gh-sources {
      display: flex;
      gap: 4px;
    }
    .gh-source {
      flex: 1;
      min-width: 0;
      padding: 4px 2px;
      border: 1px solid #1a56db;
      border-radius: 6px;
      background: #e8f0fe;
      color: #1a56db;
      font: 11px/1.2 "Segoe UI", Arial, sans-serif;
      text-align: center;
      cursor: pointer;
    }
    .gh-source[data-active="true"] {
      background: #1a56db;
      color: #ffffff;
    }
    .gh-source:disabled {
      border-color: #d1d5db;
      background: #f3f4f6;
      color: #9ca3af;
      cursor: default;
    }
    .gh-search-input {
      flex: 1;
      min-width: 0;
      padding: 4px 6px;
      border: 1px solid #1a56db;
      border-radius: 6px;
      font: inherit;
      user-select: text;
    }
    .gh-credit {
      color: #6b7280;
      font-size: 11px;
    }
    .gh-button {
      padding: 4px 10px;
      border: none;
      border-radius: 6px;
      background: #1a56db;
      color: #ffffff;
      cursor: pointer;
    }
    .gh-button.gh-secondary {
      background: #6b7280;
    }
  `;

  /**
   * Sağ üstte sürüklenebilir yardımcı panel.
   * callbacks: { onCandidateClick(word), onGuessNow(), onGuideRequest(), onGuideSearch(text),
   * onGuideTextChange(text), onGuideSourceChange(source), onGuideHide(), onOpacityChange(value) }
   */
  function createPanel(callbacks, initialOpacity) {
    const { hostElement, shadowRoot } = helper.createShadowHost(PANEL_STYLES);
    const panelElement = document.createElement("div");
    panelElement.className = "gh-panel";
    panelElement.innerHTML = `
      <div class="gh-header">
        <span class="gh-title">Gartic Helper</span>
        <button type="button" class="gh-icon-button" data-action="collapse" title="Küçült">–</button>
      </div>
      <div class="gh-body">
        <div class="gh-status" data-role="status">Hazır</div>
        <div class="gh-hint" data-role="hint"></div>
        <section data-section="guess">
          <div class="gh-candidates" data-role="candidates"></div>
          <button type="button" class="gh-button" data-action="guess-now">Şimdi tahmin et</button>
        </section>
        <section data-section="guide">
          <div class="gh-drawing-word" data-role="drawing-word">Kelime bekleniyor…</div>
          <div class="gh-credit">Çizimler: Sketchy (Sangkloy et al.); Quick, Draw! (Google, CC BY 4.0)</div>
          <div class="gh-row">
            <button type="button" class="gh-button" data-action="guide">Başka çizim</button>
          </div>
          <div class="gh-sources" data-role="guide-sources"></div>
          <div class="gh-row">
            <input type="text" class="gh-search-input" data-role="guide-search" placeholder="Çizim ara (ör. ceket)" />
            <button type="button" class="gh-button" data-action="guide-search">Ara</button>
          </div>
          <div class="gh-row">
            <label class="gh-label">Opaklık</label>
            <input type="range" min="0.05" max="0.9" step="0.05" data-role="opacity" />
            <button type="button" class="gh-button gh-secondary" data-action="guide-hide">Gizle</button>
          </div>
        </section>
      </div>`;
    shadowRoot.appendChild(panelElement);
    document.body.appendChild(hostElement);

    const query = (selector) => panelElement.querySelector(selector);
    const statusElement = query('[data-role="status"]');
    const hintElement = query('[data-role="hint"]');
    const candidatesElement = query('[data-role="candidates"]');
    const drawingWordElement = query('[data-role="drawing-word"]');
    const opacityInput = query('[data-role="opacity"]');
    opacityInput.value = String(initialOpacity);
    const GUIDE_SOURCES = [
      { id: "sketchy", label: "Sketchy" },
      { id: "quickdraw", label: "Quick Draw" },
      { id: "icon", label: "İkon" },
    ];
    const sourceButtons = new Map();
    const sourcesElement = query('[data-role="guide-sources"]');
    for (const source of GUIDE_SOURCES) {
      const sourceButton = document.createElement("button");
      sourceButton.type = "button";
      sourceButton.className = "gh-source";
      sourceButton.textContent = source.label;
      sourceButton.addEventListener("click", () => {
        if (!sourceButton.disabled) {
          callbacks.onGuideSourceChange(source.id);
        }
      });
      sourcesElement.appendChild(sourceButton);
      sourceButtons.set(source.id, sourceButton);
    }

    query('[data-action="collapse"]').addEventListener("click", () =>
      panelElement.classList.toggle("gh-collapsed"),
    );
    query('[data-action="guess-now"]').addEventListener("click", () => callbacks.onGuessNow());
    query('[data-action="guide"]').addEventListener("click", () => callbacks.onGuideRequest());
    query('[data-action="guide-hide"]').addEventListener("click", () => callbacks.onGuideHide());
    const guideSearchInput = query('[data-role="guide-search"]');
    const submitGuideSearch = () => {
      const searchText = guideSearchInput.value.trim();
      if (searchText) {
        callbacks.onGuideSearch(searchText);
      }
    };
    query('[data-action="guide-search"]').addEventListener("click", submitGuideSearch);
    // Oyunun klavye dinleyicileri yazılan harfleri yakalamasın diye olaylar panelde durdurulur.
    for (const eventName of ["keydown", "keypress", "keyup"]) {
      guideSearchInput.addEventListener(eventName, (keyEvent) => {
        keyEvent.stopPropagation();
        if (eventName === "keydown" && keyEvent.key === "Enter") {
          submitGuideSearch();
        }
      });
    }
    guideSearchInput.addEventListener("input", () => {
      callbacks.onGuideTextChange(guideSearchInput.value);
    });
    opacityInput.addEventListener("input", () =>
      callbacks.onOpacityChange(Number(opacityInput.value)),
    );
    enableDragging(hostElement, query(".gh-header"));

    return {
      setStatus(text, kind = "info") {
        statusElement.textContent = text;
        statusElement.dataset.kind = kind;
      },
      setHint(hintPattern) {
        hintElement.textContent = hintPattern ? `İpucu: ${hintPattern}` : "";
      },
      setCandidates(candidateWords) {
        candidatesElement.replaceChildren(
          ...candidateWords.map((word) => {
            const candidateButton = document.createElement("button");
            candidateButton.type = "button";
            candidateButton.className = "gh-candidate";
            candidateButton.textContent = word;
            candidateButton.addEventListener("click", () => callbacks.onCandidateClick(word));
            return candidateButton;
          }),
        );
      },
      setMode(mode) {
        panelElement.dataset.mode = mode;
      },
      setDrawingWord(word) {
        drawingWordElement.textContent = word ? `Çizilecek: ${word}` : "Kelime bekleniyor…";
      },
      setGuideSources({ counts, activeSource }) {
        for (const source of GUIDE_SOURCES) {
          const sourceButton = sourceButtons.get(source.id);
          if (counts) {
            const count = counts[source.id] ?? 0;
            sourceButton.textContent = `${source.label} ${count}`;
            sourceButton.disabled = count === 0;
          }
          sourceButton.dataset.active = activeSource === source.id ? "true" : "false";
        }
      },
      destroy() {
        hostElement.remove();
      },
    };
  }

  function enableDragging(panelElement, handleElement) {
    handleElement.addEventListener("pointerdown", (downEvent) => {
      if (downEvent.target.closest("button")) {
        return;
      }
      const panelRect = panelElement.getBoundingClientRect();
      const offsetX = downEvent.clientX - panelRect.left;
      const offsetY = downEvent.clientY - panelRect.top;
      handleElement.setPointerCapture(downEvent.pointerId);

      const handleMove = (moveEvent) => {
        panelElement.style.left = `${moveEvent.clientX - offsetX}px`;
        panelElement.style.top = `${moveEvent.clientY - offsetY}px`;
        panelElement.style.right = "auto";
      };
      const handleUp = () => {
        handleElement.removeEventListener("pointermove", handleMove);
        handleElement.removeEventListener("pointerup", handleUp);
      };
      handleElement.addEventListener("pointermove", handleMove);
      handleElement.addEventListener("pointerup", handleUp);
    });
  }

  helper.createPanel = createPanel;
})();
