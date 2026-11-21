// Content script, popup ve service worker tarafından ortak kullanılan ayarlar.
globalThis.GARTIC_HELPER_DEFAULT_SETTINGS = Object.freeze({
  guessEnabled: true,
  guideEnabled: true,
  guessIntervalMs: 3000,
  maxCandidates: 5,
  guideOpacity: 0.35,
  guideSource: "auto",
});

globalThis.loadGarticHelperSettings = async function loadGarticHelperSettings() {
  return chrome.storage.sync.get(globalThis.GARTIC_HELPER_DEFAULT_SETTINGS);
};
