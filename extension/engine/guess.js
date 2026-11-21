// Quick Draw tahmini, ipucu kalıbı ve "çok yakın" yazımını birleştirir.
(() => {
  const engine = (globalThis.GarticEngine = globalThis.GarticEngine || {});
  const CLOSE_GUESS_MAX_DISTANCE = 2;
  const CLASSIFIER_TOP_K = 20;

  function createCategoryMap(translations) {
    const turkishByCategory = new Map();
    const categoriesByTurkish = new Map();
    for (const [category, turkishWords] of Object.entries(translations)) {
      const normalizedWords = turkishWords.map((word) => engine.normalizeTurkish(word));
      turkishByCategory.set(category, normalizedWords);
      for (const turkishWord of normalizedWords) {
        const categories = categoriesByTurkish.get(turkishWord) ?? [];
        categories.push(category);
        categoriesByTurkish.set(turkishWord, categories);
      }
    }

    return {
      allTurkishWords() {
        return [...categoriesByTurkish.keys()];
      },
      toTurkish(category) {
        return turkishByCategory.get(category) ?? [];
      },
      categoriesForWord(word) {
        const normalizedWord = engine.normalizeTurkish(word);
        const exactCategories = categoriesByTurkish.get(normalizedWord);
        if (exactCategories) {
          return exactCategories;
        }
        const partialCategories = [];
        for (const wordPart of normalizedWord.split(" ")) {
          for (const category of categoriesByTurkish.get(wordPart) ?? []) {
            if (!partialCategories.includes(category)) {
              partialCategories.push(category);
            }
          }
        }
        return partialCategories;
      },
    };
  }

  function topCategories(logits, labels, topK) {
    const maxLogit = Math.max(...logits);
    const exponentials = logits.map((logit) => Math.exp(logit - maxLogit));
    const total = exponentials.reduce((sum, value) => sum + value, 0);
    return [...logits.keys()]
      .sort((left, right) => logits[right] - logits[left])
      .slice(0, topK)
      .map((index) => labels[index])
      .filter((label) => label);
  }

  function createGuesser({ wordIndex, categories, learnedCounts, labels, classify }) {
    return {
      async guess({ rgba, width, height, hintPattern, excludedWords, closeGuesses, maxCandidates }) {
        const hint = hintPattern ? engine.normalizeTurkish(hintPattern) : null;
        const normalizedCloseGuesses = (closeGuesses ?? []).map((word) =>
          engine.normalizeTurkish(word),
        );
        const excluded = new Set([
          ...(excludedWords ?? []).map((word) => engine.normalizeTurkish(word)),
          ...normalizedCloseGuesses,
        ]);
        const patternMatches = hint
          ? wordIndex
              .filterByPattern(hint)
              .filter((word) => !excluded.has(word))
              .sort(
                (left, right) => (learnedCounts[right] ?? 0) - (learnedCounts[left] ?? 0),
              )
          : [];

        const closeMatches = normalizedCloseGuesses.flatMap((closeGuess) =>
          wordIndex
            .findSimilarWords(closeGuess, CLOSE_GUESS_MAX_DISTANCE)
            .filter((word) => !hint || engine.wordMatchesPattern(word, hint)),
        );

        let modelGuesses = [];
        let warning = null;
        if (rgba) {
          try {
            const modelInput = engine.preprocessRgba(rgba, width, height);
            const logits = await classify(modelInput);
            modelGuesses = topCategories(logits, labels, CLASSIFIER_TOP_K).flatMap((category) =>
              categories.toTurkish(category),
            );
          } catch (error) {
            if (error.name !== "EmptyDrawingError") {
              warning = error.message;
            }
          }
        }
        if (hint) {
          modelGuesses = modelGuesses.filter((guess) => engine.wordMatchesPattern(guess, hint));
        }

        const candidates = [];
        const seen = new Set();
        for (const word of [...closeMatches, ...modelGuesses, ...patternMatches]) {
          if (!excluded.has(word) && !seen.has(word)) {
            seen.add(word);
            candidates.push(word);
          }
        }
        return {
          candidates: candidates.slice(0, maxCandidates),
          pattern_match_count: patternMatches.length,
          used_model: modelGuesses.length > 0,
          warning,
        };
      },
    };
  }

  engine.createCategoryMap = createCategoryMap;
  engine.createGuesser = createGuesser;
})();
