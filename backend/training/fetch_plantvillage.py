"""Download the PlantVillage subset used by AgriMind (tomato, potato, maize, bell pepper; ~220 images per class)
and the ImageNet MobileNetV3 weights, so the disease model can be retrained. Requires git.

    python training/fetch_plantvillage.py --out ../datasets
    python training/train_disease.py --data ../datasets/PlantVillage-Dataset/raw/color --weights ../datasets/mobilenetv3_large_100_ra-f55367f5.pth
"""
import argparse, random, subprocess, urllib.request
from pathlib import Path

CROPS = ("Tomato", "Potato", "Corn_(maize)", "Pepper,_bell")
WEIGHTS = "https://github.com/rwightman/pytorch-image-models/releases/download/v0.1-weights/mobilenetv3_large_100_ra-f55367f5.pth"

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="datasets")
ap.add_argument("--per-class", type=int, default=220)
a = ap.parse_args()
out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
repo = out / "PlantVillage-Dataset"
git = lambda *args: subprocess.check_output(["git", "-C", str(repo), *args], text=True)
if not repo.exists():
    subprocess.check_call(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
                           "https://github.com/spMohanty/PlantVillage-Dataset", str(repo)])
random.seed(42)
pats = []
for c in git("ls-tree", "-d", "--name-only", "HEAD", "raw/color/").splitlines():
    if c.split("/")[-1].split("___")[0] in CROPS:
        files = git("ls-tree", "--name-only", "HEAD", c + "/").splitlines()
        random.shuffle(files)
        pats += ["/" + f.replace(" ", "\\ ").replace("(", "\\(").replace(")", "\\)") for f in files[: a.per_class]]
(repo / ".git" / "info" / "sparse-checkout").write_text("\n".join(pats) + "\n", encoding="utf-8")
git("config", "core.sparseCheckoutCone", "false")
git("read-tree", "-mu", "HEAD")
w = out / Path(WEIGHTS).name
if not w.exists():
    urllib.request.urlretrieve(WEIGHTS, w)
print(f"Images: {repo / 'raw' / 'color'}\nWeights: {w}")
