importScripts(
  "../engine/words.js",
  "../engine/preprocess.js",
  "../engine/guess.js",
  "../engine/icons.js",
  "../engine/quickdraw_store.js",
  "../engine/sketchy_store.js",
  "../engine/guide.js",
  "../vendor/ort/ort.wasm.min.js",
  "../engine/runtime.js",
);

const MESSAGE_HANDLERS = {
  GUESS: async (message) => {
    const helper = await globalThis.GarticEngine.loadHelper();
    return helper.guess(message);
  },
  GUIDE: async (message) => {
    const helper = await globalThis.GarticEngine.loadHelper();
    return helper.guide(message.word, message.source);
  },
  LEARN_WORD: async (message) => {
    const helper = await globalThis.GarticEngine.loadHelper();
    return helper.learn(message.word);
  },
  HEALTH: async () => {
    const helper = await globalThis.GarticEngine.loadHelper();
    return { classifier_ready: helper.classifierReady };
  },
};

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const handler = MESSAGE_HANDLERS[message?.type];
  if (!handler) {
    return false;
  }
  handler(message)
    .then((data) => sendResponse({ ok: true, data }))
    .catch((error) => {
      console.warn("[GarticHelper]", message.type, error);
      sendResponse({ ok: false, error: error.message });
    });
  // Asenkron yanıt için kanal açık tutulur.
  return true;
});
