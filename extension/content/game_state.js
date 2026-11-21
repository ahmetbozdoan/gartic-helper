(() => {
  const helper = globalThis.GarticHelper;
  const { SELECTORS } = helper;

  const MAX_GUESS_MESSAGE_LENGTH = 40;
  const MAX_EXCLUDED_WORDS = 30;
  const INK_CHANNEL_THRESHOLD = 240;

  function isInRoom() {
    return document.querySelector(SELECTORS.roomScreen) !== null;
  }

  function isIntermission() {
    return document.querySelector(SELECTORS.timer)?.classList.contains("interval") ?? false;
  }

  function isLocalPlayerDrawing() {
    return document.querySelector(SELECTORS.localPlayerDrawing) !== null;
  }

  function readDrawingPlayerNick() {
    return document.querySelector(SELECTORS.drawingPlayerNick)?.textContent.trim() ?? "";
  }

  /** İpucunu '_' bilinmeyen harf, boşluk kelime ayırıcı olacak şekilde döndürür. Örn: "y__i_ e___" */
  function readHintPattern() {
    const wordElements = [...document.querySelectorAll(SELECTORS.hintWords)];
    if (wordElements.length === 0) {
      return null;
    }
    return wordElements
      .map((wordElement) =>
        [...wordElement.querySelectorAll("span")]
          .map((letterElement) => letterElement.textContent.trim() || "_")
          .join(""),
      )
      .join(" ");
  }

  function readCurrentRoundMessages() {
    const messageElements = [...document.querySelectorAll(SELECTORS.answerMessages)];
    let roundStartIndex = 0;
    messageElements.forEach((messageElement, index) => {
      if (messageElement.classList.contains("turn")) {
        roundStartIndex = index + 1;
      }
    });
    return messageElements.slice(roundStartIndex);
  }

  /** Mevcut turda cevap kutusuna yazılmış (yanlış) tahminler. */
  function readWrongGuesses() {
    return readCurrentRoundMessages()
      .filter((messageElement) => messageElement.classList.length === 1)
      .map((messageElement) => {
        const nickLength = messageElement.querySelector("strong")?.textContent.length ?? 0;
        return messageElement.textContent.slice(nickLength).trim();
      })
      .filter((guessText) => guessText && guessText.length <= MAX_GUESS_MESSAGE_LENGTH)
      .slice(-MAX_EXCLUDED_WORDS);
  }

  /** Mevcut turda "<strong>kelime</strong> çok yakın!" (.close) denen tahminler. */
  function readCloseGuesses() {
    return readCurrentRoundMessages()
      .filter((messageElement) => messageElement.classList.contains("close"))
      .map((messageElement) => messageElement.querySelector("strong")?.textContent.trim())
      .filter((guessText) => guessText && guessText.length <= MAX_GUESS_MESSAGE_LENGTH)
      .slice(-MAX_EXCLUDED_WORDS);
  }

  /**
   * Tur sonunda yazılan "Önceki turun cevabı: <strong>kelime</strong>" (.turn) ve
   * doğru tahminde yazılan "Cevabı buldun: <strong>kelime</strong>" (.hit) mesajları.
   */
  function readRevealedAnswerMessages() {
    return [...document.querySelectorAll(SELECTORS.answerMessages)]
      .filter(
        (messageElement) =>
          messageElement.classList.contains("turn") || messageElement.classList.contains("hit"),
      )
      .map((messageElement) => {
        const answerText = messageElement.querySelector("strong")?.textContent.trim();
        if (!answerText) {
          return null;
        }
        const messageText = messageElement.textContent;
        const labelText = messageText.slice(0, messageText.lastIndexOf(answerText)).trim();
        // "<strong>X</strong> adlı kullanıcının sırası" mesajında kalın yazı baştadır;
        // cevap mesajında ise önünde ':' ile biten bir etiket bulunur (dilden bağımsız).
        return labelText.endsWith(":") ? { messageElement, word: answerText } : null;
      })
      .filter((revealedAnswer) => revealedAnswer !== null);
  }

  /**
   * Çizim katmanlarını beyaz zemin üzerinde birleştirip küçültür.
   * inkRatio: beyaz olmayan piksel oranı; boş canvas'ı API'ye göndermemek için kullanılır.
   */
  function captureCanvas(maxSize) {
    const canvasElements = [...document.querySelectorAll(SELECTORS.drawingCanvases)];
    if (canvasElements.length === 0 || canvasElements[0].width === 0) {
      return null;
    }
    const sourceCanvas = canvasElements[0];
    const scale = Math.min(1, maxSize / Math.max(sourceCanvas.width, sourceCanvas.height));
    const outputWidth = Math.round(sourceCanvas.width * scale);
    const outputHeight = Math.round(sourceCanvas.height * scale);

    const outputCanvas = document.createElement("canvas");
    outputCanvas.width = outputWidth;
    outputCanvas.height = outputHeight;
    const context = outputCanvas.getContext("2d", { willReadFrequently: true });
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, outputWidth, outputHeight);
    for (const canvasElement of canvasElements) {
      context.drawImage(canvasElement, 0, 0, outputWidth, outputHeight);
    }

    const pixelData = context.getImageData(0, 0, outputWidth, outputHeight).data;
    let inkPixelCount = 0;
    for (let index = 0; index < pixelData.length; index += 4) {
      if (
        pixelData[index] < INK_CHANNEL_THRESHOLD ||
        pixelData[index + 1] < INK_CHANNEL_THRESHOLD ||
        pixelData[index + 2] < INK_CHANNEL_THRESHOLD
      ) {
        inkPixelCount += 1;
      }
    }

    return {
      dataUrl: outputCanvas.toDataURL("image/png"),
      inkRatio: inkPixelCount / (outputWidth * outputHeight),
    };
  }

  /** Cevap kutusuna yazar ama göndermez; Enter'a kullanıcı basar. */
  function fillAnswerInput(text) {
    const answerInput = document.querySelector(SELECTORS.answerInput);
    if (!answerInput || answerInput.disabled) {
      return false;
    }
    answerInput.focus();
    // React kontrollü input: değer native setter ile yazılmazsa React değişikliği görmez ve geri alır.
    const nativeValueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    nativeValueSetter.call(answerInput, text);
    answerInput.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
  }

  /** Gartic cevap kutusunu doğru cevaptan sonra, aralarda ve çizim başlamadan önce kilitler. */
  function canAnswer() {
    const answerInput = document.querySelector(SELECTORS.answerInput);
    return Boolean(answerInput) && !answerInput.disabled;
  }

  function submitAnswer(text) {
    if (!fillAnswerInput(text)) {
      return false;
    }
    const answerForm = document.querySelector(SELECTORS.answerInput).form;
    // React'in input değişikliğini state'e işlemesi için gönderim bir sonraki görev döngüsüne bırakılır.
    setTimeout(() => answerForm?.requestSubmit(), 0);
    return true;
  }

  helper.gameState = {
    isInRoom,
    isIntermission,
    isLocalPlayerDrawing,
    readDrawingPlayerNick,
    readHintPattern,
    readWrongGuesses,
    readCloseGuesses,
    readRevealedAnswerMessages,
    captureCanvas,
    fillAnswerInput,
    canAnswer,
    submitAnswer,
  };
})();
