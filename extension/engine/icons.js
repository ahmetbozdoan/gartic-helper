// Quick Draw'da olmayan kelimeler için Iconify simge araması. Çeviri Google, yedek MyMemory.
(() => {
  const engine = (globalThis.GarticEngine = globalThis.GarticEngine || {});

  const MAX_DICTIONARY_ALTERNATIVES = 3;
  const MAX_RELATED_QUERIES = 6;
  const MAX_ICON_NAME_SUFFIX_LENGTH = 2;
  const ENGLISH_ARTICLES = ["the ", "a ", "an "];
  const EXCLUDED_COLLECTION_CATEGORIES = new Set(["Logos"]);

  function iconNameMatchesQuery(iconName, query) {
    const nameTokens = iconName.split(":").at(-1).toLowerCase().split("-");
    const queryTokens = query.toLowerCase().replaceAll("-", " ").split(/\s+/).filter(Boolean);
    const tokensMatch = queryTokens.every((queryToken) =>
      nameTokens.some(
        (nameToken) =>
          nameToken.startsWith(queryToken) &&
          nameToken.length - queryToken.length <= MAX_ICON_NAME_SUFFIX_LENGTH,
      ),
    );
    if (tokensMatch) {
      return true;
    }
    return queryTokens.length > 1 && nameTokens.join("").includes(queryTokens.join(""));
  }

  function createIconSearch({ timeoutMs, maxResults }) {
    const iconsByWord = new Map();
    const relatedQueryByIcon = new Map();

    async function requestText(url) {
      let response;
      try {
        response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
      } catch (error) {
        throw new Error(`Simge servisine ulaşılamadı (${error.message})`);
      }
      if (!response.ok) {
        throw new Error(`Simge servisi ${response.status}: ${url}`);
      }
      return response.text();
    }

    async function translateToEnglish(word) {
      const quotedWord = encodeURIComponent(word);
      try {
        const response = JSON.parse(
          await requestText(
            `https://translate.googleapis.com/translate_a/single?client=gtx&sl=tr&tl=en&dt=t&dt=bd&q=${quotedWord}`,
          ),
        );
        const translations = [response[0].map((segment) => String(segment[0])).join("")];
        for (const dictionaryEntry of response[1] ?? []) {
          translations.push(
            ...dictionaryEntry[1]
              .slice(0, MAX_DICTIONARY_ALTERNATIVES)
              .map((term) => String(term)),
          );
        }
        return cleanTranslations(word, translations);
      } catch (googleError) {
        console.warn("[GarticHelper] Google çevirisi başarısız:", word, googleError);
      }
      try {
        const response = JSON.parse(
          await requestText(
            `https://api.mymemory.translated.net/get?q=${quotedWord}&langpair=tr|en`,
          ),
        );
        return cleanTranslations(word, [String(response.responseData.translatedText)]);
      } catch (error) {
        console.warn("[GarticHelper] Kelime çevrilemedi:", word, error);
        return [];
      }
    }

    function cleanTranslations(word, translations) {
      const cleaned = [];
      const seen = new Set();
      for (const translation of translations) {
        let cleanedTranslation = translation.trim().toLowerCase();
        for (const article of ENGLISH_ARTICLES) {
          if (cleanedTranslation.startsWith(article)) {
            cleanedTranslation = cleanedTranslation.slice(article.length);
          }
        }
        if (cleanedTranslation && cleanedTranslation !== word && !seen.has(cleanedTranslation)) {
          seen.add(cleanedTranslation);
          cleaned.push(cleanedTranslation);
        }
      }
      return cleaned;
    }

    async function searchIcons(query) {
      const response = JSON.parse(
        await requestText(
          `https://api.iconify.design/search?query=${encodeURIComponent(query)}&limit=64`,
        ),
      );
      const collections = response.collections ?? {};
      return (response.icons ?? []).filter((iconName) => {
        const collection = iconName.split(":")[0];
        return (
          !EXCLUDED_COLLECTION_CATEGORIES.has(collections[collection]?.category) &&
          iconNameMatchesQuery(iconName, query)
        );
      });
    }

    async function collectIcons(queries) {
      const queryByIcon = new Map();
      const iconCountByCollection = new Map();
      for (const query of queries) {
        if (!query || queryByIcon.size >= maxResults) {
          break;
        }
        let iconNames = [];
        try {
          iconNames = await searchIcons(query);
        } catch (error) {
          console.warn("[GarticHelper] Simge araması başarısız:", query, error);
          continue;
        }
        for (const iconName of iconNames) {
          const collection = iconName.split(":")[0];
          if (queryByIcon.has(iconName) || (iconCountByCollection.get(collection) ?? 0) >= 2) {
            continue;
          }
          if (queryByIcon.size >= maxResults) {
            break;
          }
          iconCountByCollection.set(collection, (iconCountByCollection.get(collection) ?? 0) + 1);
          queryByIcon.set(iconName, query);
        }
      }
      return queryByIcon;
    }

    return {
      async findIcons(word) {
        if (iconsByWord.has(word)) {
          return iconsByWord.get(word);
        }
        const translations = await translateToEnglish(word);
        const queries = [];
        const seenQueries = new Set();
        const addQuery = (query) => {
          if (query && !seenQueries.has(query)) {
            seenQueries.add(query);
            queries.push(query);
          }
        };
        for (const englishWord of translations) {
          addQuery(englishWord);
          if (englishWord.endsWith("s") && englishWord.length > 3) {
            addQuery(englishWord.slice(0, -1));
          }
        }
        addQuery(word);
        let queryByIcon = await collectIcons(queries);
        if (queryByIcon.size === 0 && translations.length > 0) {
          let relatedWords = [];
          try {
            const response = JSON.parse(
              await requestText(
                `https://api.datamuse.com/words?max=20&ml=${encodeURIComponent(translations[0])}`,
              ),
            );
            relatedWords = response.map((entry) => String(entry.word)).slice(0, MAX_RELATED_QUERIES);
          } catch (error) {
            console.warn("[GarticHelper] Yakın anlamlı kelimeler alınamadı:", translations[0], error);
          }
          queryByIcon = await collectIcons(relatedWords);
          for (const [iconName, query] of queryByIcon) {
            relatedQueryByIcon.set(iconName, query);
          }
        }
        const foundIcons = [...queryByIcon.keys()];
        if (foundIcons.length > 0) {
          iconsByWord.set(word, foundIcons);
        }
        return foundIcons;
      },
      relatedQueryFor(iconName) {
        return relatedQueryByIcon.get(iconName) ?? null;
      },
      async fetchIconSvg(iconName) {
        const [prefix, name] = iconName.split(":");
        return requestText(
          `https://api.iconify.design/${encodeURIComponent(prefix)}/${encodeURIComponent(name)}.svg?height=256`,
        );
      },
    };
  }

  function svgToDataUrl(svgMarkup) {
    const bytes = new TextEncoder().encode(svgMarkup);
    let binary = "";
    for (const byte of bytes) {
      binary += String.fromCharCode(byte);
    }
    return `data:image/svg+xml;base64,${btoa(binary)}`;
  }

  engine.createIconSearch = createIconSearch;
  engine.svgToDataUrl = svgToDataUrl;
})();
