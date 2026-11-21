// Gartic görüntüsünü Quick Draw 28x28 bitmap'ine çevirir. Python drawing_preprocessor ile aynı adımlar.
(() => {
  const engine = (globalThis.GarticEngine = globalThis.GarticEngine || {});

  const QUICKDRAW_IMAGE_SIZE = 28;
  const QUICKDRAW_DRAWING_SPAN = 256;
  const QUICKDRAW_TOTAL_PADDING = 2 * 16 + 16;
  const QUICKDRAW_LINE_WIDTH = 16;
  const INTERMEDIATE_SIZE = QUICKDRAW_IMAGE_SIZE * 4;
  const INK_THRESHOLD = 40;
  const INTERMEDIATE_INK_THRESHOLD = 20;
  const COLOR_EDGE_THRESHOLD = 40;
  const FILL_EROSION_RATIO = 0.02;

  function createEmptyDrawingError() {
    const error = new Error("Canvas'ta çizim yok");
    error.name = "EmptyDrawingError";
    return error;
  }

  function rankFilter(pixels, width, height, windowSize, pickMax) {
    const radius = Math.floor(windowSize / 2);
    const output = new Uint8Array(pixels.length);
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        let value = pickMax ? 0 : 255;
        for (let offsetY = -radius; offsetY <= radius; offsetY += 1) {
          const sampleY = y + offsetY;
          if (sampleY < 0 || sampleY >= height) {
            value = pickMax ? value : 0;
            continue;
          }
          for (let offsetX = -radius; offsetX <= radius; offsetX += 1) {
            const sampleX = x + offsetX;
            const sample = sampleX < 0 || sampleX >= width ? 0 : pixels[sampleY * width + sampleX];
            value = pickMax ? Math.max(value, sample) : Math.min(value, sample);
          }
        }
        output[y * width + x] = value;
      }
    }
    return output;
  }

  // Pillow Image.Resampling.BOX: önce yatay, sonra dikey; 8 bit katsayılar 22 bit sabit noktadadır.
  const RESAMPLE_PRECISION_BITS = 22;

  function boxCoeffs(inSize, outSize) {
    const scale = inSize / outSize;
    const filterScale = Math.max(scale, 1);
    const support = 0.5 * filterScale;
    const ksize = Math.ceil(support) * 2 + 1;
    const bounds = new Int32Array(outSize * 2);
    const coefficients = new Int32Array(outSize * ksize);
    const fixedUnit = 2 ** RESAMPLE_PRECISION_BITS;
    for (let outIndex = 0; outIndex < outSize; outIndex += 1) {
      const center = (outIndex + 0.5) * scale;
      let xmin = Math.trunc(center - support + 0.5);
      if (xmin < 0) {
        xmin = 0;
      }
      let count = Math.trunc(center + support + 0.5);
      if (count > inSize) {
        count = inSize;
      }
      count -= xmin;
      const inverseScale = 1 / filterScale;
      let weightTotal = 0;
      const weights = [];
      for (let offset = 0; offset < count; offset += 1) {
        const position = (offset + xmin - center + 0.5) * inverseScale;
        const weight = position > -0.5 && position <= 0.5 ? 1 : 0;
        weights.push(weight);
        weightTotal += weight;
      }
      for (let offset = 0; offset < count; offset += 1) {
        const normalized = weightTotal ? weights[offset] / weightTotal : 0;
        coefficients[outIndex * ksize + offset] = Math.trunc(0.5 + normalized * fixedUnit);
      }
      bounds[outIndex * 2] = xmin;
      bounds[outIndex * 2 + 1] = count;
    }
    return { ksize, bounds, coefficients };
  }

  function clipResampled(value) {
    const shifted = Math.trunc(value / 2 ** RESAMPLE_PRECISION_BITS);
    if (shifted < 0) {
      return 0;
    }
    return shifted > 255 ? 255 : shifted;
  }

  function resizeBox(pixels, sourceWidth, sourceHeight, targetWidth, targetHeight) {
    const horizontal = boxCoeffs(sourceWidth, targetWidth);
    const horizontalPixels = new Uint8Array(targetWidth * sourceHeight);
    const roundingBias = 2 ** (RESAMPLE_PRECISION_BITS - 1);
    for (let y = 0; y < sourceHeight; y += 1) {
      for (let x = 0; x < targetWidth; x += 1) {
        const xmin = horizontal.bounds[x * 2];
        const count = horizontal.bounds[x * 2 + 1];
        let sum = roundingBias;
        for (let offset = 0; offset < count; offset += 1) {
          sum +=
            pixels[y * sourceWidth + xmin + offset] *
            horizontal.coefficients[x * horizontal.ksize + offset];
        }
        horizontalPixels[y * targetWidth + x] = clipResampled(sum);
      }
    }
    const vertical = boxCoeffs(sourceHeight, targetHeight);
    const output = new Uint8Array(targetWidth * targetHeight);
    for (let y = 0; y < targetHeight; y += 1) {
      const ymin = vertical.bounds[y * 2];
      const count = vertical.bounds[y * 2 + 1];
      for (let x = 0; x < targetWidth; x += 1) {
        let sum = roundingBias;
        for (let offset = 0; offset < count; offset += 1) {
          sum +=
            horizontalPixels[(ymin + offset) * targetWidth + x] *
            vertical.coefficients[y * vertical.ksize + offset];
        }
        output[y * targetWidth + x] = clipResampled(sum);
      }
    }
    return output;
  }

  // skimage _fast_skeletonize ile aynı Zhang-Suen tablosu. 1 ve 3 ilk turda, 2 ve 3 ikinci turda silinir.
  const SKELETON_LUT = Uint8Array.from(
    atob(
      "AAAAAQAAAQMAAAMBAQABAwAAAAAAAAAAAgACAAMAAwMAAAAAAAAAAAMAAAAAAAAAAAAAAAAAAAACAAAAAwACAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAAAAAAACAAAAAgAAAAMAAAAAAAAAAwAAAAMAAgAAAAMBAAABAwAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAQMBAAAAAAAAAAAAAAAAAAACAAAAAAAAAAAAAAAAAAAAAgMBAwAAAQMAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAACAwABAAAAAQAAAAAAAAAAAwMAAQAAAAACAgAAAgAAAA==",
    ),
    (character) => character.charCodeAt(0),
  );

  function skeletonize(mask, width, height) {
    const paddedWidth = width + 2;
    const paddedHeight = height + 2;
    const skeleton = new Uint8Array(paddedWidth * paddedHeight);
    const cleaned = new Uint8Array(paddedWidth * paddedHeight);
    for (let y = 0; y < height; y += 1) {
      skeleton.set(mask.subarray(y * width, (y + 1) * width), (y + 1) * paddedWidth + 1);
    }
    cleaned.set(skeleton);
    let pixelRemoved = true;
    while (pixelRemoved) {
      pixelRemoved = false;
      for (let pass = 0; pass < 2; pass += 1) {
        const firstPass = pass === 0;
        for (let y = 1; y < paddedHeight - 1; y += 1) {
          for (let x = 1; x < paddedWidth - 1; x += 1) {
            if (!skeleton[y * paddedWidth + x]) {
              continue;
            }
            const neighborCode = SKELETON_LUT[
              skeleton[(y - 1) * paddedWidth + (x - 1)] +
                2 * skeleton[(y - 1) * paddedWidth + x] +
                4 * skeleton[(y - 1) * paddedWidth + (x + 1)] +
                8 * skeleton[y * paddedWidth + (x + 1)] +
                16 * skeleton[(y + 1) * paddedWidth + (x + 1)] +
                32 * skeleton[(y + 1) * paddedWidth + x] +
                64 * skeleton[(y + 1) * paddedWidth + (x - 1)] +
                128 * skeleton[y * paddedWidth + (x - 1)]
            ];
            if (
              neighborCode === 3 ||
              (neighborCode === 1 && firstPass) ||
              (neighborCode === 2 && !firstPass)
            ) {
              cleaned[y * paddedWidth + x] = 0;
              pixelRemoved = true;
            }
          }
        }
        skeleton.set(cleaned);
      }
    }
    const output = new Uint8Array(width * height);
    for (let y = 0; y < height; y += 1) {
      output.set(skeleton.subarray((y + 1) * paddedWidth + 1, (y + 1) * paddedWidth + 1 + width), y * width);
    }
    return output;
  }

  function detectColorEdges(rgba, width, height) {
    const edges = new Uint8Array(width * height);
    const channelDelta = (left, right) =>
      Math.max(
        Math.abs(rgba[left] - rgba[right]),
        Math.abs(rgba[left + 1] - rgba[right + 1]),
        Math.abs(rgba[left + 2] - rgba[right + 2]),
      );
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const offset = (y * width + x) * 4;
        if (x + 1 < width && channelDelta(offset, offset + 4) > COLOR_EDGE_THRESHOLD) {
          edges[y * width + x] = 1;
          edges[y * width + x + 1] = 1;
        }
        if (y + 1 < height && channelDelta(offset, offset + width * 4) > COLOR_EDGE_THRESHOLD) {
          edges[y * width + x] = 1;
          edges[(y + 1) * width + x] = 1;
        }
      }
    }
    return edges;
  }

  function preprocessRgba(rgba, width, height) {
    const inkMask = new Uint8Array(width * height);
    let hasInk = false;
    for (let index = 0; index < width * height; index += 1) {
      const offset = index * 4;
      const darkest = Math.min(rgba[offset], rgba[offset + 1], rgba[offset + 2]);
      if (255 - darkest > INK_THRESHOLD) {
        inkMask[index] = 1;
        hasInk = true;
      }
    }
    if (!hasInk) {
      throw createEmptyDrawingError();
    }

    const erosionSize = Math.max(3, (Math.trunc(Math.max(width, height) * FILL_EROSION_RATIO) | 1));
    const eroded = rankFilter(inkMask.map((value) => value * 255), width, height, erosionSize, false);
    const edges = detectColorEdges(rgba, width, height);
    const strokeMask = new Uint8Array(width * height);
    for (let index = 0; index < strokeMask.length; index += 1) {
      const isStroke = (inkMask[index] && eroded[index] === 0) || edges[index];
      strokeMask[index] = isStroke ? 1 : 0;
    }
    const centerlines = skeletonize(strokeMask, width, height);

    let minY = height;
    let maxY = -1;
    let minX = width;
    let maxX = -1;
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        if (!centerlines[y * width + x]) {
          continue;
        }
        minY = Math.min(minY, y);
        maxY = Math.max(maxY, y);
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
      }
    }
    if (maxY < 0) {
      throw createEmptyDrawingError();
    }

    const croppedHeight = maxY - minY + 1;
    const croppedWidth = maxX - minX + 1;
    const drawingSpan = Math.max(croppedHeight, croppedWidth);
    const padding = Math.round(
      (drawingSpan * QUICKDRAW_TOTAL_PADDING) / QUICKDRAW_DRAWING_SPAN / 2,
    );
    const squareSize = drawingSpan + 2 * padding;
    const square = new Uint8Array(squareSize * squareSize);
    const offsetY = Math.floor((squareSize - croppedHeight) / 2);
    const offsetX = Math.floor((squareSize - croppedWidth) / 2);
    for (let y = 0; y < croppedHeight; y += 1) {
      for (let x = 0; x < croppedWidth; x += 1) {
        if (centerlines[(minY + y) * width + minX + x]) {
          square[(offsetY + y) * squareSize + offsetX + x] = 255;
        }
      }
    }

    let intermediate = resizeBox(
      square,
      squareSize,
      squareSize,
      INTERMEDIATE_SIZE,
      INTERMEDIATE_SIZE,
    );
    for (let index = 0; index < intermediate.length; index += 1) {
      intermediate[index] = intermediate[index] > INTERMEDIATE_INK_THRESHOLD ? 255 : 0;
    }
    const lineWidthPixels =
      (INTERMEDIATE_SIZE * QUICKDRAW_LINE_WIDTH) /
      (QUICKDRAW_DRAWING_SPAN + QUICKDRAW_TOTAL_PADDING);
    const dilationSize = Math.trunc(lineWidthPixels) | 1;
    if (dilationSize >= 3) {
      intermediate = rankFilter(
        intermediate,
        INTERMEDIATE_SIZE,
        INTERMEDIATE_SIZE,
        dilationSize,
        true,
      );
    }
    const finalPixels = resizeBox(
      intermediate,
      INTERMEDIATE_SIZE,
      INTERMEDIATE_SIZE,
      QUICKDRAW_IMAGE_SIZE,
      QUICKDRAW_IMAGE_SIZE,
    );
    const modelInput = new Float32Array(QUICKDRAW_IMAGE_SIZE * QUICKDRAW_IMAGE_SIZE);
    for (let index = 0; index < finalPixels.length; index += 1) {
      modelInput[index] = finalPixels[index] / 255;
    }
    return modelInput;
  }

  engine.preprocessRgba = preprocessRgba;
})();
