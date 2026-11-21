"""
Quick Draw 28x28 bitmapleri üzerinde küçük bir CNN eğitir ve ONNX olarak dışa aktarır.

Önce: python scripts/download_quickdraw.py
Kullanım: python scripts/train_quickdraw_classifier.py --epochs 8
Çıktılar: models/quickdraw_cnn.onnx, models/quickdraw_labels.json
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CATEGORY_TRANSLATIONS_PATH = BACKEND_ROOT / "data" / "quickdraw_categories_tr.json"
BITMAPS_DIR = BACKEND_ROOT / "data" / "quickdraw" / "bitmaps"
MODELS_DIR = BACKEND_ROOT / "models"
ONNX_MODEL_PATH = MODELS_DIR / "quickdraw_cnn.onnx"
LABELS_PATH = MODELS_DIR / "quickdraw_labels.json"
IMAGE_SIZE = 28
MAX_TRAIN_SHIFT_PIXELS = 2


class QuickDrawCnn(nn.Module):
    def __init__(self, class_count: int) -> None:
        super().__init__()

        def conv_block(in_channels: int, out_channels: int) -> nn.Sequential:
            return nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(out_channels),
                nn.ReLU(inplace=True),
            )

        self.features = nn.Sequential(
            conv_block(1, 32),
            nn.MaxPool2d(2),  # 14x14
            conv_block(32, 64),
            conv_block(64, 64),
            nn.MaxPool2d(2),  # 7x7
            conv_block(64, 128),
            nn.MaxPool2d(2),  # 3x3
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(128 * 3 * 3, 512),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(512, class_count),
        )

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(images))


def load_dataset(categories: list[str], samples_per_category: int) -> tuple[np.ndarray, np.ndarray]:
    bitmap_batches: list[np.ndarray] = []
    label_batches: list[np.ndarray] = []
    for label_index, category in enumerate(categories):
        bitmap_path = BITMAPS_DIR / f"{category.replace(' ', '_')}.npy"
        if not bitmap_path.exists():
            raise FileNotFoundError(
                f"Bitmap dosyası yok: {bitmap_path}. Önce download_quickdraw.py çalıştırın."
            )
        bitmaps = np.load(bitmap_path)[:samples_per_category]
        bitmap_batches.append(bitmaps)
        label_batches.append(np.full(len(bitmaps), label_index, dtype=np.int64))
    return np.concatenate(bitmap_batches), np.concatenate(label_batches)


def to_model_input(bitmap_batch: torch.Tensor) -> torch.Tensor:
    return bitmap_batch.view(-1, 1, IMAGE_SIZE, IMAGE_SIZE).float().div_(255.0)


def random_shift(images: torch.Tensor) -> torch.Tensor:
    """Gartic çizimlerinin ortalanması kusursuz olmayacağı için hafif kaydırma artırımı."""
    shift_y, shift_x = np.random.randint(-MAX_TRAIN_SHIFT_PIXELS, MAX_TRAIN_SHIFT_PIXELS + 1, 2)
    return torch.roll(images, shifts=(int(shift_y), int(shift_x)), dims=(2, 3))


@torch.no_grad()
def evaluate(
    model: nn.Module, bitmaps: torch.Tensor, labels: torch.Tensor, batch_size: int
) -> tuple[float, float]:
    model.eval()
    top1_correct = 0
    top3_correct = 0
    for start in range(0, len(bitmaps), batch_size):
        logits = model(to_model_input(bitmaps[start : start + batch_size]))
        batch_labels = labels[start : start + batch_size]
        top3_predictions = logits.topk(3, dim=1).indices
        top1_correct += (top3_predictions[:, 0] == batch_labels).sum().item()
        top3_correct += (top3_predictions == batch_labels[:, None]).any(dim=1).sum().item()
    return top1_correct / len(bitmaps), top3_correct / len(bitmaps)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-per-category", type=int, default=4000)
    parser.add_argument("--validation-ratio", type=float, default=0.05)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=3e-3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    categories = list(json.loads(CATEGORY_TRANSLATIONS_PATH.read_text(encoding="utf-8")))

    print(f"Veri yükleniyor: {len(categories)} kategori", flush=True)
    bitmaps, labels = load_dataset(categories, args.samples_per_category)
    permutation = np.random.permutation(len(bitmaps))
    bitmaps, labels = bitmaps[permutation], labels[permutation]
    validation_count = int(len(bitmaps) * args.validation_ratio)
    validation_bitmaps = torch.from_numpy(bitmaps[:validation_count])
    validation_labels = torch.from_numpy(labels[:validation_count])
    train_bitmaps = torch.from_numpy(bitmaps[validation_count:])
    train_labels = torch.from_numpy(labels[validation_count:])
    print(f"Eğitim: {len(train_bitmaps)}, doğrulama: {validation_count}", flush=True)

    model = QuickDrawCnn(len(categories))
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    steps_per_epoch = (len(train_bitmaps) + args.batch_size - 1) // args.batch_size
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer,
        max_lr=args.learning_rate,
        total_steps=args.epochs * steps_per_epoch,
    )
    loss_function = nn.CrossEntropyLoss(label_smoothing=0.1)

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_started_at = time.time()
        epoch_permutation = torch.randperm(len(train_bitmaps))
        running_loss = 0.0
        for step in range(steps_per_epoch):
            batch_indices = epoch_permutation[step * args.batch_size : (step + 1) * args.batch_size]
            images = random_shift(to_model_input(train_bitmaps[batch_indices]))
            loss = loss_function(model(images), train_labels[batch_indices])
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            scheduler.step()
            running_loss += loss.item()

        top1_accuracy, top3_accuracy = evaluate(
            model, validation_bitmaps, validation_labels, args.batch_size * 4
        )
        print(
            f"Epoch {epoch}/{args.epochs} | loss={running_loss / steps_per_epoch:.3f} "
            f"| top1={top1_accuracy:.3f} top3={top3_accuracy:.3f} "
            f"| {time.time() - epoch_started_at:.0f} sn",
            flush=True,
        )

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model.eval()
    torch.onnx.export(
        model,
        (torch.zeros(1, 1, IMAGE_SIZE, IMAGE_SIZE),),
        str(ONNX_MODEL_PATH),
        input_names=["input"],
        output_names=["logits"],
        dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )
    LABELS_PATH.write_text(json.dumps(categories, ensure_ascii=False, indent=1), "utf-8")
    print(f"Model kaydedildi: {ONNX_MODEL_PATH}")


if __name__ == "__main__":
    main()
