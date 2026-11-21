const settingsForm = document.getElementById("settings-form");
const healthStatusElement = document.getElementById("health-status");
const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("guide-search");
const guideImage = document.getElementById("guide-image");
const guideEmpty = document.getElementById("guide-empty");
const guideStatus = document.getElementById("guide-status");
const sourceButtons = [...document.querySelectorAll(".source")];

let guideSource = "auto";
let lastWord = "";
let searchInFlight = false;

function setHealthStatus(text, kind) {
  healthStatusElement.textContent = text;
  healthStatusElement.dataset.kind = kind;
}

function setGuideStatus(text, kind = "info") {
  guideStatus.textContent = text;
  guideStatus.dataset.kind = kind;
}

function setGuideSources(counts, activeSource) {
  for (const button of sourceButtons) {
    const sourceId = button.dataset.source;
    if (counts) {
      const count = counts[sourceId] ?? 0;
      const label = sourceId === "quickdraw" ? "Quick Draw" : sourceId === "icon" ? "İkon" : "Sketchy";
      button.textContent = `${label} ${count}`;
      button.disabled = count === 0;
    }
    button.dataset.active = activeSource === sourceId ? "true" : "false";
  }
}

async function requestGuide(word) {
  if (!word || searchInFlight || !globalThis.chrome?.runtime?.sendMessage) {
    return;
  }
  searchInFlight = true;
  setGuideStatus("Aranıyor…");
  try {
    const response = await chrome.runtime.sendMessage({
      type: "GUIDE",
      word,
      source: guideSource,
    });
    if (!response?.ok) {
      setGuideStatus(response?.error ?? "Bağlantı hatası", "error");
      return;
    }
    const result = response.data;
    setGuideSources(result.counts, result.source);
    if (!result.image_data_url) {
      guideImage.hidden = true;
      guideEmpty.hidden = false;
      setGuideStatus(result.error ?? "Çizim bulunamadı", "error");
      return;
    }
    guideImage.src = globalThis.fitSketchyDrawing(result.image_data_url);
    guideImage.hidden = false;
    guideEmpty.hidden = true;
    setGuideStatus(result.category);
  } catch (error) {
    setGuideStatus(error.message, "error");
  } finally {
    searchInFlight = false;
  }
}

async function fillForm() {
  if (!globalThis.chrome?.storage) {
    return;
  }
  const settings = await globalThis.loadGarticHelperSettings();
  settingsForm.guessEnabled.checked = settings.guessEnabled;
  settingsForm.guideEnabled.checked = settings.guideEnabled;
  settingsForm.guessIntervalSeconds.value = Math.round(settings.guessIntervalMs / 1000);
  settingsForm.maxCandidates.value = settings.maxCandidates;
}

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const searchText = searchInput.value.trim();
  if (!searchText) {
    return;
  }
  if (searchText !== lastWord) {
    guideSource = "auto";
  }
  lastWord = searchText;
  requestGuide(searchText);
});

searchInput.addEventListener("input", () => {
  const typedText = searchInput.value.trim();
  if (!typedText || typedText === lastWord || guideSource === "auto") {
    return;
  }
  guideSource = "auto";
  setGuideSources(null, null);
});

for (const button of sourceButtons) {
  button.addEventListener("click", () => {
    const searchText = searchInput.value.trim();
    if (!searchText || button.disabled) {
      return;
    }
    guideSource = button.dataset.source;
    lastWord = searchText;
    requestGuide(searchText);
  });
}

document.getElementById("guide-next").addEventListener("click", () => {
  const searchText = searchInput.value.trim();
  if (!searchText) {
    return;
  }
  lastWord = searchText;
  requestGuide(searchText);
});

settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!globalThis.chrome?.storage) {
    return;
  }
  await chrome.storage.sync.set({
    guessEnabled: settingsForm.guessEnabled.checked,
    guideEnabled: settingsForm.guideEnabled.checked,
    guessIntervalMs: Number(settingsForm.guessIntervalSeconds.value) * 1000,
    maxCandidates: Number(settingsForm.maxCandidates.value),
  });
  setHealthStatus("Kaydedildi", "ok");
});

document.getElementById("health-check").addEventListener("click", async () => {
  setHealthStatus("Kontrol ediliyor…", "info");
  if (!globalThis.chrome?.runtime?.sendMessage) {
    setHealthStatus("Bağlantı hatası", "error");
    return;
  }
  const response = await chrome.runtime.sendMessage({ type: "HEALTH" });
  if (!response?.ok) {
    setHealthStatus(response?.error ?? "Bağlantı hatası", "error");
    return;
  }
  const modelLabel = response.data.classifier_ready ? "Model hazır" : "Model yüklenemedi";
  setHealthStatus(modelLabel, response.data.classifier_ready ? "ok" : "error");
});

fillForm();
