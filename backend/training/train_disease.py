"""Train the AgriMind crop-disease classifier (transfer learning, MobileNetV3-Large).

Dataset: PlantVillage (Hughes & Salathe, 2015), colour images, 19 classes from
tomato, potato, maize and bell pepper. Images: https://github.com/spMohanty/PlantVillage-Dataset

Usage:
    python training/train_disease.py --data <path to raw/color> --weights <mobilenetv3_large_100_ra-f55367f5.pth>

Outputs (backend/models/):
    disease_model.pt        weights + class list + input size
    disease_metrics.json    accuracy, macro F1, per-class report, confusion matrix (held-out test split)
Uses CUDA automatically when available.
"""
import argparse, json, os, random, time
from pathlib import Path

import numpy as np
import timm
import torch
import torch.nn as nn
from PIL import Image
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

CROPS = ("Tomato", "Potato", "Corn_(maize)", "Pepper,_bell")
IMG = 192
MEAN, STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)


class Leaves(Dataset):
    def __init__(self, items, tf):
        self.items, self.tf = items, tf

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        p, y = self.items[i]
        return self.tf(Image.open(p).convert("RGB")), y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--per-class", type=int, default=220)
    ap.add_argument("--head-epochs", type=int, default=3)
    ap.add_argument("--ft-epochs", type=int, default=4)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "models"))
    a = ap.parse_args()

    random.seed(42); np.random.seed(42); torch.manual_seed(42)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.set_num_threads(max(1, os.cpu_count() or 1))

    classes = sorted(d.name for d in Path(a.data).iterdir() if d.is_dir() and d.name.split("___")[0] in CROPS)
    items = []
    for ci, c in enumerate(classes):
        files = sorted(f for f in (Path(a.data) / c).iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png"))
        random.shuffle(files)
        items += [(str(f), ci) for f in files[: a.per_class]]
    ys = [y for _, y in items]
    tr, rest = train_test_split(items, test_size=0.30, stratify=ys, random_state=42)
    va, te = train_test_split(rest, test_size=0.50, stratify=[y for _, y in rest], random_state=42)
    print(f"{len(classes)} classes | train {len(tr)} val {len(va)} test {len(te)} | device {device}")

    tf_train = transforms.Compose([
        transforms.RandomResizedCrop(IMG, scale=(0.7, 1.0)), transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(), transforms.ColorJitter(0.3, 0.3, 0.3, 0.05),
        transforms.RandomRotation(20), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    tf_eval = transforms.Compose([transforms.Resize((IMG, IMG)), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    nw = 2 if os.name != "nt" else 0
    dl_tr = DataLoader(Leaves(tr, tf_train), batch_size=32, shuffle=True, num_workers=nw)
    dl_va = DataLoader(Leaves(va, tf_eval), batch_size=64, num_workers=nw)
    dl_te = DataLoader(Leaves(te, tf_eval), batch_size=64, num_workers=nw)

    model = timm.create_model("mobilenetv3_large_100", pretrained=False)
    model.load_state_dict(torch.load(a.weights, map_location="cpu"))
    model.reset_classifier(len(classes))
    model.to(device)
    crit = nn.CrossEntropyLoss(label_smoothing=0.1)

    def evaluate(dl):
        model.eval(); P, Y = [], []
        with torch.no_grad():
            for x, y in dl:
                P += model(x.to(device)).argmax(1).cpu().tolist(); Y += y.tolist()
        return Y, P

    def run(epochs, params, lr, tag):
        opt = torch.optim.AdamW(params, lr=lr, weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, epochs * len(dl_tr)))
        for ep in range(epochs):
            model.train(); t0 = time.time(); tot = 0.0
            for x, y in dl_tr:
                opt.zero_grad(); loss = crit(model(x.to(device)), y.to(device)); loss.backward(); opt.step(); sched.step()
                tot += loss.item() * len(y)
            Y, P = evaluate(dl_va)
            hist.append({"phase": tag, "epoch": ep + 1, "train_loss": round(tot / len(tr), 4),
                         "val_accuracy": round(accuracy_score(Y, P), 4), "seconds": round(time.time() - t0, 1)})
            print(hist[-1], flush=True)

    hist = []
    for p in model.parameters(): p.requires_grad = False
    for p in model.get_classifier().parameters(): p.requires_grad = True
    run(a.head_epochs, model.get_classifier().parameters(), 3e-3, "head")
    for n, p in model.named_parameters():
        if n.startswith(("blocks.5", "blocks.6", "conv_head", "classifier")): p.requires_grad = True
    run(a.ft_epochs, [p for p in model.parameters() if p.requires_grad], 5e-4, "fine-tune")

    Y, P = evaluate(dl_te)
    rep = classification_report(Y, P, labels=list(range(len(classes))), target_names=classes, output_dict=True, zero_division=0)
    metrics = {
        "model": "MobileNetV3-Large (ImageNet-pretrained, timm) fine-tuned",
        "dataset": "PlantVillage colour images (Hughes & Salathe 2015), 19 classes: tomato, potato, maize, bell pepper",
        "image_size": IMG, "split": {"train": len(tr), "val": len(va), "test": len(te)},
        "test_accuracy": round(accuracy_score(Y, P), 4),
        "test_macro_f1": round(f1_score(Y, P, average="macro"), 4),
        "test_weighted_f1": round(f1_score(Y, P, average="weighted"), 4),
        "per_class": {c: {k: round(v, 4) for k, v in rep[c].items()} for c in classes},
        "confusion_matrix": confusion_matrix(Y, P, labels=list(range(len(classes)))).tolist(),
        "classes": classes, "history": hist, "device": device,
        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "limitations": ("PlantVillage photos are single leaves on plain lab backgrounds. Accuracy on field photos with "
                        "cluttered backgrounds, multiple leaves or other crops will be considerably lower."),
    }
    os.makedirs(a.out, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "classes": classes, "image_size": IMG, "arch": "mobilenetv3_large_100"},
               os.path.join(a.out, "disease_model.pt"))
    json.dump(metrics, open(os.path.join(a.out, "disease_metrics.json"), "w"), indent=2)
    # keep a few held-out test images for demonstrating the UI
    sd = Path(a.out).parent / "data" / "sample_leaves"; sd.mkdir(parents=True, exist_ok=True)
    seen = set()
    for p, y in te:
        if y not in seen:
            seen.add(y); Image.open(p).convert("RGB").save(sd / f"{classes[y].replace(',', '').replace(' ', '_')}.jpg", quality=90)
    print("TEST", metrics["test_accuracy"], metrics["test_macro_f1"])


if __name__ == "__main__":
    main()
