// Eklentiye konan Sketchy SVG alt kümesini okur. Tam arşiv pakette değildir.
(() => {
  const engine = (globalThis.GarticEngine = globalThis.GarticEngine || {});
  const svgCache = new Map();

  function createSketchyLoader(index) {
    const drawingCounts = index.drawing_counts ?? {};
    return async function loadSketchyCategory(category) {
      const cached = svgCache.get(category);
      if (cached) {
        return cached;
      }
      const count = drawingCounts[category] ?? 0;
      const svgs = [];
      for (let number = 1; number <= count; number += 1) {
        const svgUrl = chrome.runtime.getURL(`assets/sketchy/${category}/${number}.svg`);
        const response = await fetch(svgUrl);
        if (!response.ok) {
          throw new Error(`${category} SVG okunamadı (${response.status})`);
        }
        svgs.push(await response.text());
      }
      svgCache.set(category, svgs);
      return svgs;
    };
  }

  engine.createSketchyLoader = createSketchyLoader;
})();
