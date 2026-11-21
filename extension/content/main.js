(() => {
  const helper = globalThis.GarticHelper;
  const { gameState, guideOverlay } = helper;

  const TICK_INTERVAL_MS = 1000;
  const CANVAS_CAPTURE_MAX_SIZE = 384;
  // Bu orandan az mürekkep varsa çizim henüz anlamlı değildir, API'ye gönderilmez.
  const MIN_INK_RATIO = 0.004;
  const OPACITY_SAVE_DEBOUNCE_MS = 500;

  let settings = { ...globalThis.GARTIC_HELPER_DEFAULT_SETTINGS };
  let panel = null;
  let roundKey = null;
  let lastCanvasDataUrl = null;
  let lastHintPattern = null;
  let lastCloseGuessesKey = "";
  let lastGuessAt = 0;
  let isGuessInFlight = false;
  let isGuideInFlight = false;
  let guideRequestedForWord = null;
  let lastGuideWord = null;
  let currentDrawingWord = null;
  // Seçim ekranı ara (intermission) sırasında da görünebildiği için tur sıfırlamasında silinmez.
  let chosenDrawingWord = null;
  let opacitySaveTimeoutId = null;
  // Aynı cevap mesajının her tick'te tekrar sayılmaması için işlenen DOM öğeleri tutulur.
  const learnedAnswerElements = new WeakSet();
  const EXTENSION_RELOAD_FLAG = "garticHelperContextReload";

  // Eklenti chrome://extensions üzerinden yenilenince açık sekmedeki eski kodun bağlantısı kopar.
  function isExtensionConnected() {
    try {
      return Boolean(chrome.runtime?.id);
    } catch {
      return false;
    }
  }

  function reloadPageForNewExtension() {
    if (sessionStorage.getItem(EXTENSION_RELOAD_FLAG) === "1") {
      return false;
    }
    sessionStorage.setItem(EXTENSION_RELOAD_FLAG, "1");
    location.reload();
    return true;
  }

  if (isExtensionConnected()) {
    sessionStorage.removeItem(EXTENSION_RELOAD_FLAG);
  }

  async function sendToBackground(message) {
    if (!isExtensionConnected()) {
      if (reloadPageForNewExtension()) {
        throw new Error("Eklenti yenilendi, sayfa yenileniyor");
      }
      throw new Error("Eklenti bağlantısı yok. Eklentiyi ve bu sekmeyi yenileyin");
    }
    let response;
    try {
      response = await chrome.runtime.sendMessage(message);
    } catch (error) {
      if (!isExtensionConnected() && reloadPageForNewExtension()) {
        throw new Error("Eklenti yenilendi, sayfa yenileniyor");
      }
      throw new Error(`Eklenti bağlantısı koptu, sayfayı yenileyin (${error.message})`);
    }
    if (!response?.ok) {
      throw new Error(response?.error ?? "Bilinmeyen hata");
    }
    return response.data;
  }

  function resetRound() {
    lastCanvasDataUrl = null;
    lastHintPattern = null;
    lastCloseGuessesKey = "";
    guideRequestedForWord = null;
    guideOverlay.hide();
    panel?.setCandidates([]);
    panel?.setStatus("Yeni tur");
  }

  async function requestGuess(hintPattern, isForced) {
    if (isGuessInFlight) {
      return;
    }
    const closeGuesses = gameState.readCloseGuesses();
    const closeGuessesKey = closeGuesses.join("|");
    // "Çok yakın" mesajı güçlü bir ipucu olduğu için tahmin aralığı beklenmeden yenilenir.
    const isCloseGuessesChanged = closeGuessesKey !== lastCloseGuessesKey;
    if (
      !isForced &&
      !(settings.guessEnabled && isCloseGuessesChanged) &&
      (!settings.guessEnabled || Date.now() - lastGuessAt < settings.guessIntervalMs)
    ) {
      return;
    }

    const capture = gameState.captureCanvas(CANVAS_CAPTURE_MAX_SIZE);
    const hasInk = capture !== null && capture.inkRatio >= MIN_INK_RATIO;
    const isCanvasChanged = hasInk && capture.dataUrl !== lastCanvasDataUrl;
    const isHintChanged = hintPattern !== lastHintPattern;
    if (!isForced && !isCanvasChanged && !isHintChanged && !isCloseGuessesChanged) {
      return;
    }
    if (!hasInk && !hintPattern && closeGuesses.length === 0) {
      return;
    }

    lastGuessAt = Date.now();
    lastHintPattern = hintPattern;
    lastCloseGuessesKey = closeGuessesKey;
    if (hasInk) {
      lastCanvasDataUrl = capture.dataUrl;
    }
    const requestRoundKey = roundKey;
    isGuessInFlight = true;
    panel?.setStatus("Tahmin ediliyor…", "busy");

    try {
      const response = await sendToBackground({
        type: "GUESS",
        imageDataUrl: hasInk ? capture.dataUrl : null,
        hintPattern,
        excludedWords: gameState.readWrongGuesses(),
        closeGuesses,
        maxCandidates: settings.maxCandidates,
      });
      if (requestRoundKey !== roundKey || !panel) {
        return;
      }
      panel.setCandidates(response.candidates);
      if (response.warning) {
        panel.setStatus(`Uyarı: ${response.warning}`, "error");
      } else {
        const sourceLabel = response.used_model ? "model + ipucu" : "ipucu";
        panel.setStatus(`${response.candidates.length} öneri (${sourceLabel})`);
      }
    } catch (error) {
      panel?.setStatus(error.message, "error");
    } finally {
      isGuessInFlight = false;
    }
  }

  async function requestGuide(word) {
    if (isGuideInFlight) {
      return;
    }
    guideRequestedForWord = word;
    lastGuideWord = word;
    isGuideInFlight = true;
    const requestRoundKey = roundKey;
    panel?.setStatus(`"${word}" için kılavuz hazırlanıyor…`, "busy");

    try {
      const response = await sendToBackground({
        type: "GUIDE",
        word,
        source: settings.guideSource,
      });
      if (requestRoundKey !== roundKey) {
        return;
      }
      panel?.setGuideSources({ counts: response.counts, activeSource: response.source });
      if (!response.image_data_url) {
        panel?.setStatus(response.error ?? "Çizim bulunamadı", "error");
        return;
      }
      guideOverlay.show(response.image_data_url, settings.guideOpacity);
      panel?.setStatus(`Kılavuz hazır (${response.category}), farklısı için tekrar basın`);
    } catch (error) {
      panel?.setStatus(error.message, "error");
    } finally {
      isGuideInFlight = false;
    }
  }

  function learnRevealedAnswers() {
    for (const { messageElement, word } of gameState.readRevealedAnswerMessages()) {
      if (learnedAnswerElements.has(messageElement)) {
        continue;
      }
      learnedAnswerElements.add(messageElement);
      sendToBackground({ type: "LEARN_WORD", word }).catch((error) =>
        console.warn("[GarticHelper] Kelime kaydedilemedi:", word, error),
      );
    }
  }

  function handleDrawingTurn(hintPattern) {
    // Çizen oyuncuya ipucu alanında kelimenin tüm harfleri gösterilir; yoksa seçim ekranında
    // tıklanan kelime kullanılır.
    const hintWord = hintPattern && !hintPattern.includes("_") ? hintPattern : null;
    currentDrawingWord = hintWord ?? chosenDrawingWord;
    panel.setDrawingWord(currentDrawingWord);
    if (!currentDrawingWord) {
      return;
    }
    if (settings.guideEnabled && guideRequestedForWord !== currentDrawingWord) {
      console.info("[GarticHelper] Çizilecek kelime algılandı:", currentDrawingWord);
      requestGuide(currentDrawingWord);
    }
  }

  document.addEventListener(
    "click",
    (event) => {
      const choiceButton = event.target.closest?.(helper.SELECTORS.wordChoiceButton);
      const chosenWord = choiceButton?.closest(".word")?.querySelector("span")?.textContent.trim();
      if (chosenWord) {
        chosenDrawingWord = chosenWord;
      }
    },
    true,
  );

  const panelCallbacks = {
    onCandidateClick(word) {
      if (!gameState.submitAnswer(word)) {
        panel?.setStatus("Cevap kutusu şu an kapalı", "error");
      }
    },
    onGuessNow() {
      requestGuess(gameState.readHintPattern(), true);
    },
    onGuideRequest() {
      if (currentDrawingWord) {
        requestGuide(currentDrawingWord);
      } else {
        panel?.setStatus("Kelime henüz algılanmadı", "error");
      }
    },
    onGuideSearch(searchText) {
      if (searchText !== lastGuideWord) {
        settings.guideSource = "auto";
      }
      requestGuide(searchText);
      // Aranan çizimin, bir sonraki tick'te turun kelimesiyle otomatik ezilmesini önler.
      guideRequestedForWord = currentDrawingWord;
    },
    onGuideTextChange(text) {
      const typedText = text.trim();
      if (!typedText || typedText === lastGuideWord || settings.guideSource === "auto") {
        return;
      }
      settings.guideSource = "auto";
      chrome.storage.sync.set({ guideSource: "auto" });
      panel?.setGuideSources({ counts: null, activeSource: null });
    },
    onGuideSourceChange(source) {
      settings.guideSource = source;
      chrome.storage.sync.set({ guideSource: source });
      if (!lastGuideWord) {
        return;
      }
      requestGuide(lastGuideWord);
      guideRequestedForWord = currentDrawingWord;
    },
    onGuideHide() {
      guideOverlay.hide();
    },
    onOpacityChange(opacity) {
      settings.guideOpacity = opacity;
      guideOverlay.setOpacity(opacity);
      clearTimeout(opacitySaveTimeoutId);
      opacitySaveTimeoutId = setTimeout(
        () => chrome.storage.sync.set({ guideOpacity: opacity }),
        OPACITY_SAVE_DEBOUNCE_MS,
      );
    },
  };

  function tick() {
    if (!gameState.isInRoom()) {
      if (panel) {
        panel.destroy();
        panel = null;
        guideOverlay.hide();
        roundKey = null;
      }
      return;
    }
    if (!panel) {
      panel = helper.createPanel(panelCallbacks, settings.guideOpacity);
    }
    learnRevealedAnswers();

    const hintPattern = gameState.readHintPattern();
    const isIntermission = gameState.isIntermission();
    const isDrawing = gameState.isLocalPlayerDrawing();
    // İpucu tur ortasında belirebildiği için tur anahtarına dahil edilmez; turlar arasında her zaman ara vardır.
    const nextRoundKey = `${gameState.readDrawingPlayerNick()}|${isIntermission}`;
    if (nextRoundKey !== roundKey) {
      roundKey = nextRoundKey;
      resetRound();
    }

    panel.setHint(isDrawing ? null : hintPattern);
    panel.setMode(isDrawing ? "draw" : "guess");
    if (isIntermission) {
      return;
    }
    if (isDrawing) {
      handleDrawingTurn(hintPattern);
    } else {
      chosenDrawingWord = null;
      currentDrawingWord = null;
      if (gameState.canAnswer()) {
        requestGuess(hintPattern, false);
      } else if (!isGuessInFlight) {
        panel.setStatus("Cevap kutusu kapalı, tahmin beklemede");
      }
    }
  }

  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== "sync") {
      return;
    }
    for (const [settingName, change] of Object.entries(changes)) {
      settings[settingName] = change.newValue;
    }
    guideOverlay.setOpacity(settings.guideOpacity);
  });

  globalThis.loadGarticHelperSettings().then((loadedSettings) => {
    settings = loadedSettings;
    setInterval(tick, TICK_INTERVAL_MS);
  });
})();
