// Kelime için seçilen kaynaktan çizim döndürür. Otomatik sıra: Sketchy, Quick Draw, ikon.
(() => {
  const engine = (globalThis.GarticEngine = globalThis.GarticEngine || {});
  const SVG_VIEWBOX = "-12 -12 280 280";
  const SVG_STROKE_WIDTH = 4;

  function renderDrawingSvg(drawing) {
    const polylines = drawing
      .map((stroke) => {
        const [xs, ys] = stroke;
        const points = xs.map((x, index) => `${x},${ys[index]}`).join(" ");
        return `<polyline points="${points}"/>`;
      })
      .join("");
    return (
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${SVG_VIEWBOX}">` +
      `<g fill="none" stroke="#000" stroke-width="${SVG_STROKE_WIDTH}" ` +
      `stroke-linecap="round" stroke-linejoin="round">${polylines}</g></svg>`
    );
  }

  function spellingCandidates(wordIndex, normalizedWord) {
    if (!normalizedWord.includes(engine.AMBIGUOUS_DOTLESS_I)) {
      return [normalizedWord];
    }
    return [
      ...new Set([
        ...wordIndex.filterByPattern(normalizedWord),
        normalizedWord,
        normalizedWord.replaceAll(engine.AMBIGUOUS_DOTLESS_I, "i"),
      ]),
    ];
  }

  function createGuide({
    wordIndex,
    categories,
    iconSearch,
    loadDrawings,
    sketchyCategories,
    loadSketchSvgs,
  }) {
    const cursorByWord = new Map();
    const loadedByWord = new Map();

    function nextItem(cursorKey, items) {
      const cursor = cursorByWord.get(cursorKey) ?? 0;
      const chosen = items[cursor % items.length];
      cursorByWord.set(cursorKey, cursor + 1);
      return { chosen, position: (cursor % items.length) + 1 };
    }

    async function loadSketchy(candidates) {
      const sketches = [];
      if (!loadSketchSvgs || !sketchyCategories) {
        return sketches;
      }
      for (const candidateWord of candidates) {
        for (const category of sketchyCategories.categoriesForWord(candidateWord)) {
          for (const svg of await loadSketchSvgs(category)) {
            sketches.push({ category, svg });
          }
        }
        if (sketches.length > 0) {
          break;
        }
      }
      return sketches;
    }

    async function loadQuickDraw(candidates) {
      const drawings = [];
      for (const candidateWord of candidates) {
        for (const category of categories.categoriesForWord(candidateWord)) {
          for (const drawing of await loadDrawings(category)) {
            drawings.push({ category, drawing });
          }
        }
        if (drawings.length > 0) {
          break;
        }
      }
      return drawings;
    }

    async function loadIcons(candidates) {
      if (!iconSearch) {
        return [];
      }
      for (const candidateWord of candidates) {
        const iconNames = await iconSearch.findIcons(candidateWord);
        if (iconNames.length > 0) {
          return iconNames;
        }
      }
      return [];
    }

    function loadAll(normalizedWord, candidates) {
      const existing = loadedByWord.get(normalizedWord);
      if (existing) {
        return existing;
      }
      const pending = Promise.all([
        loadSketchy(candidates).catch(() => []),
        loadQuickDraw(candidates).catch(() => []),
        loadIcons(candidates).catch(() => []),
      ]).then(([sketchy, quickdraw, icon]) => ({ sketchy, quickdraw, icon }));
      loadedByWord.set(normalizedWord, pending);
      return pending;
    }

    return {
      async guide(word, source = "auto") {
        const normalizedWord = engine.normalizeTurkish(word);
        const candidates = spellingCandidates(wordIndex, normalizedWord);
        const selectedSource = ["sketchy", "quickdraw", "icon"].includes(source) ? source : "auto";
        const buckets = await loadAll(normalizedWord, candidates);
        const counts = {
          sketchy: buckets.sketchy.length,
          quickdraw: buckets.quickdraw.length,
          icon: buckets.icon.length,
        };
        const resolvedSource =
          selectedSource === "auto"
            ? ["sketchy", "quickdraw", "icon"].find((name) => counts[name] > 0) ?? null
            : selectedSource;
        const base = { word: normalizedWord, counts, source: resolvedSource };
        const items = resolvedSource ? buckets[resolvedSource] : [];
        if (!resolvedSource || items.length === 0) {
          const sourceNames = { sketchy: "Sketchy", quickdraw: "Quick Draw", icon: "ikon" };
          const missingLabel = sourceNames[selectedSource];
          return {
            ...base,
            source: null,
            category: null,
            image_data_url: null,
            error: missingLabel
              ? `'${normalizedWord}' için ${missingLabel} bulunamadı`
              : `'${normalizedWord}' için çizim bulunamadı`,
          };
        }
        const { chosen, position } = nextItem(`${resolvedSource}:${normalizedWord}`, items);
        if (resolvedSource === "icon") {
          const relatedQuery = iconSearch.relatedQueryFor(chosen);
          const sourceLabel = relatedQuery ? `ikon, yakın anlam '${relatedQuery}'` : "ikon";
          return {
            ...base,
            category: `${sourceLabel} · ${position}/${items.length}: ${chosen}`,
            image_data_url: engine.svgToDataUrl(await iconSearch.fetchIconSvg(chosen)),
          };
        }
        if (resolvedSource === "sketchy") {
          return {
            ...base,
            category: `sketchy ${chosen.category} · ${position}/${items.length}`,
            image_data_url: engine.svgToDataUrl(chosen.svg),
          };
        }
        return {
          ...base,
          category: `${chosen.category} · ${position}/${items.length}`,
          image_data_url: engine.svgToDataUrl(renderDrawingSvg(chosen.drawing)),
        };
      },
    };
  }

  engine.createGuide = createGuide;
})();
