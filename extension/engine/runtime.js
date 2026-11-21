// Model, kelime listesi ve kılavuz verisini eklenti paketinden yükler. Python sunucusu gerekmez.
(() => {
  const engine = (globalThis.GarticEngine = globalThis.GarticEngine || {});

  function assetUrl(fileName) {
    return chrome.runtime.getURL(`assets/${fileName}`);
  }

  async function readJson(fileName) {
    const response = await fetch(assetUrl(fileName));
    if (!response.ok) {
      throw new Error(`${fileName} okunamadı (${response.status})`);
    }
    return response.json();
  }

  async function decodeDataUrl(dataUrl) {
    const imageBlob = await (await fetch(dataUrl)).blob();
    const bitmap = await createImageBitmap(imageBlob);
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const context = canvas.getContext("2d", { willReadFrequently: true });
    context.drawImage(bitmap, 0, 0);
    const { data, width, height } = context.getImageData(0, 0, bitmap.width, bitmap.height);
    bitmap.close();
    return { rgba: data, width, height };
  }

  let helperPromise = null;

  function loadHelper() {
    if (!helperPromise) {
      helperPromise = buildHelper().catch((error) => {
        helperPromise = null;
        throw error;
      });
    }
    return helperPromise;
  }

  async function buildHelper() {
    ort.env.wasm.wasmPaths = chrome.runtime.getURL("vendor/ort/");
    ort.env.wasm.numThreads = 1;
    ort.env.wasm.simd = true;
    ort.env.wasm.proxy = false;

    const [wordList, translations, bundledLearned, labels, sketchyIndex] = await Promise.all([
      readJson("words_tr.json"),
      readJson("quickdraw_categories_tr.json"),
      readJson("learned_words.json"),
      readJson("quickdraw_labels.json"),
      readJson("sketchy/index.json"),
    ]);
    const stored = await chrome.storage.local.get("learnedWordCounts");
    const learnedCounts = {
      ...bundledLearned,
      ...(stored.learnedWordCounts ?? {}),
    };
    const categories = engine.createCategoryMap(translations);
    const sketchyCategories = engine.createCategoryMap(sketchyIndex.translations);
    const wordIndex = engine.createWordIndex([
      ...wordList,
      ...categories.allTurkishWords(),
      ...sketchyCategories.allTurkishWords(),
      ...Object.keys(learnedCounts),
    ]);

    let session = null;
    let loadError = null;
    try {
      session = await ort.InferenceSession.create(assetUrl("quickdraw_cnn.onnx"), {
        executionProviders: ["wasm"],
      });
    } catch (error) {
      loadError = error;
      console.warn("[GarticHelper] Çizim modeli yüklenemedi:", error);
    }

    const guesser = engine.createGuesser({
      wordIndex,
      categories,
      learnedCounts,
      labels,
      async classify(modelInput) {
        if (!session) {
          throw new Error(
            `Çizim modeli yüklenemedi${loadError ? `: ${loadError.message}` : ""}`,
          );
        }
        const inputName = session.inputNames[0];
        const outputs = await session.run({
          [inputName]: new ort.Tensor("float32", modelInput, [1, 1, 28, 28]),
        });
        return outputs[session.outputNames[0]].data;
      },
    });
    const guide = engine.createGuide({
      wordIndex,
      categories,
      sketchyCategories,
      loadSketchSvgs: engine.createSketchyLoader(sketchyIndex),
      loadDrawings: engine.loadQuickDrawCategory,
      iconSearch: engine.createIconSearch({ timeoutMs: 8000, maxResults: 12 }),
    });

    return {
      classifierReady: session !== null,
      async guess(message) {
        const image = message.imageDataUrl ? await decodeDataUrl(message.imageDataUrl) : null;
        return guesser.guess({
          rgba: image?.rgba ?? null,
          width: image?.width ?? 0,
          height: image?.height ?? 0,
          hintPattern: message.hintPattern,
          excludedWords: message.excludedWords,
          closeGuesses: message.closeGuesses,
          maxCandidates: message.maxCandidates,
        });
      },
      guide(word, source) {
        return guide.guide(word, source);
      },
      async learn(word) {
        const normalizedWord = engine.normalizeTurkish(word);
        if (!normalizedWord) {
          throw new Error("Öğrenilecek kelime boş");
        }
        learnedCounts[normalizedWord] = (learnedCounts[normalizedWord] ?? 0) + 1;
        const isNew = wordIndex.addWord(normalizedWord);
        await chrome.storage.local.set({ learnedWordCounts: learnedCounts });
        return { word: normalizedWord, seen_count: learnedCounts[normalizedWord], is_new: isNew };
      },
    };
  }

  engine.loadHelper = loadHelper;
})();
