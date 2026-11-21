// Kelime listesi, ipucu kalıbı ve "çok yakın" yazım benzerliği. Python word_matcher ile aynı kurallar.
(() => {
  const engine = (globalThis.GarticEngine = globalThis.GarticEngine || {});
  const UNKNOWN_LETTERS = new Set(["_", "?", "*"]);
  const AMBIGUOUS_DOTLESS_I = "ı";

  function normalizeTurkish(text) {
    // JS toLowerCase "I" harfini "i" yapar; Türkçede "I" -> "ı" olmalı. "İ" birleşik nokta üretmesin.
    const lowered = String(text).replaceAll("I", "ı").replaceAll("İ", "i").toLowerCase();
    return lowered.replace(/\s+/g, " ").trim();
  }

  function wordMatchesPattern(word, pattern) {
    if (word.length !== pattern.length) {
      return false;
    }
    for (let index = 0; index < word.length; index += 1) {
      const patternChar = pattern[index];
      const wordChar = word[index];
      if (UNKNOWN_LETTERS.has(patternChar)) {
        if (wordChar === " ") {
          return false;
        }
      } else if (
        wordChar !== patternChar &&
        !(patternChar === AMBIGUOUS_DOTLESS_I && wordChar === "i")
      ) {
        return false;
      }
    }
    return true;
  }

  function editDistance(firstWord, secondWord) {
    let previousRow = Array.from({ length: secondWord.length + 1 }, (_, index) => index);
    for (let firstIndex = 1; firstIndex <= firstWord.length; firstIndex += 1) {
      const currentRow = [firstIndex];
      for (let secondIndex = 1; secondIndex <= secondWord.length; secondIndex += 1) {
        const substitutionCost = firstWord[firstIndex - 1] === secondWord[secondIndex - 1] ? 0 : 1;
        currentRow.push(
          Math.min(
            previousRow[secondIndex] + 1,
            currentRow[secondIndex - 1] + 1,
            previousRow[secondIndex - 1] + substitutionCost,
          ),
        );
      }
      previousRow = currentRow;
    }
    return previousRow[previousRow.length - 1];
  }

  function createWordIndex(rawWords) {
    const words = [];
    const wordSet = new Set();
    for (const rawWord of rawWords) {
      if (typeof rawWord !== "string" || !rawWord.trim()) {
        continue;
      }
      const word = normalizeTurkish(rawWord);
      if (!word || wordSet.has(word)) {
        continue;
      }
      wordSet.add(word);
      words.push(word);
    }

    return {
      get words() {
        return words;
      },
      filterByPattern(pattern) {
        return words.filter((word) => wordMatchesPattern(word, pattern));
      },
      findSimilarWords(word, maxDistance) {
        const normalizedWord = normalizeTurkish(word);
        const foldedWord = normalizedWord.replaceAll(AMBIGUOUS_DOTLESS_I, "i");
        const distances = new Map();
        for (const candidate of words) {
          if (Math.abs(candidate.length - normalizedWord.length) > maxDistance) {
            continue;
          }
          const distance = editDistance(
            foldedWord,
            candidate.replaceAll(AMBIGUOUS_DOTLESS_I, "i"),
          );
          if (candidate !== normalizedWord && distance <= maxDistance) {
            distances.set(candidate, distance);
          }
        }
        return [...distances.keys()].sort(
          (left, right) => distances.get(left) - distances.get(right),
        );
      },
      addWord(word) {
        const normalizedWord = normalizeTurkish(word);
        if (!normalizedWord || wordSet.has(normalizedWord)) {
          return false;
        }
        wordSet.add(normalizedWord);
        words.push(normalizedWord);
        return true;
      },
    };
  }

  engine.normalizeTurkish = normalizeTurkish;
  engine.wordMatchesPattern = wordMatchesPattern;
  engine.createWordIndex = createWordIndex;
  engine.AMBIGUOUS_DOTLESS_I = AMBIGUOUS_DOTLESS_I;
})();
