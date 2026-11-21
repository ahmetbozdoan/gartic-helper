// Quick Draw simplified ndjson'undan tanınmış çizimleri indirir ve IndexedDB'de tutar.
// Tam veri kümesi (onlarca GB) eklenti paketine koyulmaz.
(() => {
  const engine = (globalThis.GarticEngine = globalThis.GarticEngine || {});
  const SIMPLIFIED_URL =
    "https://storage.googleapis.com/quickdraw_dataset/full/simplified/{category}.ndjson";
  const DRAWINGS_PER_CATEGORY = 24;
  const CHUNK_BYTES = 256 * 1024;
  const MAX_BYTES = 2 * 1024 * 1024;
  const DB_NAME = "gartic-helper-quickdraw";
  const STORE_NAME = "categories";

  let databasePromise = null;
  const loadsInFlight = new Map();

  function openDatabase() {
    if (!databasePromise) {
      databasePromise = new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, 1);
        request.onupgradeneeded = () => {
          request.result.createObjectStore(STORE_NAME);
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
    }
    return databasePromise;
  }

  function withStore(mode, action) {
    return openDatabase().then(
      (database) =>
        new Promise((resolve, reject) => {
          const transaction = database.transaction(STORE_NAME, mode);
          const request = action(transaction.objectStore(STORE_NAME));
          request.onsuccess = () => resolve(request.result);
          request.onerror = () => reject(request.error);
        }),
    );
  }

  function categoryUrl(category) {
    return SIMPLIFIED_URL.replace("{category}", encodeURIComponent(category));
  }

  function parseRecognizedDrawings(buffer, limit) {
    const text = new TextDecoder().decode(buffer);
    const newline = text.lastIndexOf("\n");
    if (newline < 0) {
      return { drawings: [], remainder: buffer };
    }
    const drawings = [];
    for (const line of text.slice(0, newline).split("\n")) {
      if (!line) {
        continue;
      }
      let record;
      try {
        record = JSON.parse(line);
      } catch {
        continue;
      }
      if (!record.recognized || !Array.isArray(record.drawing)) {
        continue;
      }
      const strokes = record.drawing
        .filter((stroke) => stroke.length >= 2 && stroke[0].length === stroke[1].length)
        .map((stroke) => [stroke[0], stroke[1]]);
      if (strokes.length > 0) {
        drawings.push(strokes);
      }
      if (drawings.length >= limit) {
        break;
      }
    }
    return { drawings, remainder: new TextEncoder().encode(text.slice(newline + 1)) };
  }

  async function downloadDrawings(category) {
    const url = categoryUrl(category);
    const probe = await fetch(url, { headers: { Range: "bytes=0-0" } });
    const totalBytes = Number((probe.headers.get("Content-Range") ?? "").split("/").at(-1));
    if (!probe.ok || !totalBytes) {
      throw new Error(`Quick Draw dosyası okunamadı (${category})`);
    }
    const drawings = [];
    let remainder = new Uint8Array();
    let offset = 0;
    const byteLimit = Math.min(totalBytes, MAX_BYTES);
    while (drawings.length < DRAWINGS_PER_CATEGORY && offset < byteLimit) {
      const end = Math.min(offset + CHUNK_BYTES, totalBytes) - 1;
      const response = await fetch(url, { headers: { Range: `bytes=${offset}-${end}` } });
      if (!response.ok) {
        throw new Error(`Quick Draw indirme hatası ${response.status} (${category})`);
      }
      const chunk = new Uint8Array(await response.arrayBuffer());
      offset += chunk.length;
      const combined = new Uint8Array(remainder.length + chunk.length);
      combined.set(remainder);
      combined.set(chunk, remainder.length);
      const parsed = parseRecognizedDrawings(combined, DRAWINGS_PER_CATEGORY - drawings.length);
      drawings.push(...parsed.drawings);
      remainder = parsed.remainder;
    }
    if (drawings.length === 0) {
      throw new Error(`'${category}' için tanınmış çizim bulunamadı`);
    }
    return drawings;
  }

  function loadCategory(category) {
    const pending = loadsInFlight.get(category);
    if (pending) {
      return pending;
    }
    const load = (async () => {
      const cached = await withStore("readonly", (store) => store.get(category));
      if (cached?.length) {
        return cached;
      }
      const drawings = await downloadDrawings(category);
      await withStore("readwrite", (store) => store.put(drawings, category));
      return drawings;
    })();
    loadsInFlight.set(category, load);
    load.finally(() => loadsInFlight.delete(category));
    return load;
  }

  engine.loadQuickDrawCategory = loadCategory;
})();
