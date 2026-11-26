"""Crop disease inference with the trained MobileNetV3 model."""
import io
import json
import os
import threading

import numpy as np
from PIL import Image, UnidentifiedImageError

from .core import MODELS

INFO = {
    "Bacterial_spot": ("Bacterial spot", "Xanthomonas spp. (bacterium)", "Use disease-free seed, avoid overhead irrigation, rotate crops, copper-based sprays slow spread. Fungicides do not control bacteria."),
    "Early_blight": ("Early blight", "Alternaria solani (fungus)", "Remove infected lower leaves, mulch, rotate 2–3 years away from solanaceous crops, protectant fungicide (e.g. mancozeb/chlorothalonil) per label."),
    "Late_blight": ("Late blight", "Phytophthora infestans (oomycete)", "Act fast: remove infected plants, avoid overhead watering, protectant mancozeb and systemic metalaxyl + mancozeb per label; spreads rapidly in cool humid weather."),
    "Leaf_Mold": ("Leaf mould", "Passalora fulva (fungus)", "Improve ventilation and lower humidity (especially in polyhouses), avoid wetting leaves, resistant varieties, recommended fungicides."),
    "Septoria_leaf_spot": ("Septoria leaf spot", "Septoria lycopersici (fungus)", "Remove infected leaves, avoid working in wet fields, mulch, rotate, protectant fungicide sprays."),
    "Spider_mites Two-spotted_spider_mite": ("Two-spotted spider mite", "Tetranychus urticae (mite)", "Raise humidity with water sprays, conserve predatory mites, wettable sulphur or recommended acaricide per label."),
    "Target_Spot": ("Target spot", "Corynespora cassiicola (fungus)", "Remove residues, improve air flow, avoid excess nitrogen, recommended fungicides."),
    "Tomato_Yellow_Leaf_Curl_Virus": ("Tomato yellow leaf curl virus", "Begomovirus spread by whitefly", "No cure: uproot infected plants early, net-house nurseries, yellow sticky traps, whitefly management, tolerant hybrids."),
    "Tomato_mosaic_virus": ("Tomato mosaic virus", "Tobamovirus (mechanical / seed)", "Remove infected plants, disinfect tools and hands, certified seed, crop rotation."),
    "Cercospora_leaf_spot Gray_leaf_spot": ("Gray leaf spot", "Cercospora zeae-maydis (fungus)", "Rotate crops, bury residue, resistant hybrids, fungicide if severe before tasseling."),
    "Common_rust_": ("Common rust", "Puccinia sorghi (fungus)", "Resistant hybrids, timely sowing; fungicide only on susceptible hybrids with early infection."),
    "Northern_Leaf_Blight": ("Northern leaf blight", "Exserohilum turcicum (fungus)", "Resistant hybrids, rotation and residue management, fungicide at early appearance."),
    "healthy": ("Healthy", "—", "No disease detected. Keep monitoring weekly, especially after rain."),
}
CROP_NAMES = {"Tomato": "Tomato", "Potato": "Potato", "Corn_(maize)": "Maize", "Pepper,_bell": "Bell pepper"}


class DiseaseModel:
    def __init__(self):
        self.lock = threading.Lock()
        self.model = None
        self.metrics = json.loads((MODELS / "disease_metrics.json").read_text()) if (MODELS / "disease_metrics.json").exists() else None

    def _load(self):
        # Lite mode (small servers): ONNX Runtime, no PyTorch needed.
        if (MODELS / "disease_model.onnx").exists():
            try:
                import onnxruntime as ort
                meta = json.loads((MODELS / "disease_classes.json").read_text())
                so = ort.SessionOptions()
                so.enable_cpu_mem_arena = False  # return activation memory after each call instead of caching it
                so.enable_mem_pattern = False
                so.intra_op_num_threads = int(os.environ.get("ONNX_THREADS", "1"))
                so.inter_op_num_threads = 1
                self.session = ort.InferenceSession(str(MODELS / "disease_model.onnx"), sess_options=so,
                                                    providers=["CPUExecutionProvider"])
                self.classes, self.size, self.device, self.backend = meta["classes"], meta["image_size"], "cpu", "onnx"
                self.model = self.session
                return
            except ImportError:
                pass
        import timm
        import torch
        ck = torch.load(MODELS / "disease_model.pt", map_location="cpu", weights_only=False)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        m = timm.create_model(ck["arch"], pretrained=False, num_classes=len(ck["classes"]))
        m.load_state_dict(ck["state_dict"])
        self.model, self.classes, self.size = m.eval().to(self.device), ck["classes"], ck["image_size"]
        self.backend = "torch"

    def available(self):
        return (MODELS / "disease_model.pt").exists() or (MODELS / "disease_model.onnx").exists()

    def predict(self, raw: bytes):
        with self.lock:
            if self.model is None:
                self._load()
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGB")
        except (UnidentifiedImageError, OSError):
            raise ValueError("The file is not a readable image.")
        if self.backend == "onnx":
            a = np.asarray(img.resize((self.size, self.size), Image.BILINEAR), dtype=np.float32) / 255.0
            a = (a - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
            x = a.transpose(2, 0, 1)[None].astype(np.float32)
            x = np.concatenate([x, x[..., ::-1]], axis=0)  # original + horizontal flip
            logits = self.session.run(None, {"input": np.ascontiguousarray(x)})[0].sum(axis=0) / 2
            e = np.exp(logits - logits.max())
            p = e / e.sum()
        else:
            import torch
            from torchvision import transforms
            tf = transforms.Compose([transforms.Resize((self.size, self.size)), transforms.ToTensor(),
                                     transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225))])
            x = tf(img).unsqueeze(0).to(self.device)
            with torch.no_grad():
                # light test-time augmentation: original + horizontal flip
                logits = self.model(x) + self.model(torch.flip(x, dims=[3]))
                p = torch.softmax(logits / 2, dim=1)[0].cpu().numpy()
        order = np.argsort(-p)[:3]
        preds = [self._describe(self.classes[i], float(p[i])) for i in order]
        entropy = float(-(p * np.log(p + 1e-12)).sum() / np.log(len(p)))
        warnings = []
        top = preds[0]["confidence"]
        if top < 0.5:
            warnings.append("Low confidence: the model is unsure. Take a clearer photo of a single leaf in good light, or consult an expert.")
        elif top < 0.75:
            warnings.append("Moderate confidence: check the alternatives below and confirm symptoms in the field.")
        g = self._leaf_ratio(img)
        if g < 0.15:
            warnings.append("The image does not look like a close-up of a plant leaf; predictions may be meaningless.")
        return {"predictions": preds, "top": preds[0], "uncertainty": round(entropy, 4), "leaf_pixel_ratio": round(g, 3),
                "warnings": warnings, "supported_crops": sorted(set(CROP_NAMES.values())),
                "device": self.device, "model": "MobileNetV3-Large fine-tuned on PlantVillage (19 classes)"}

    @staticmethod
    def _leaf_ratio(img):
        a = np.asarray(img.resize((96, 96)).convert("HSV")).astype(float)
        h, s, v = a[..., 0] * 360 / 255, a[..., 1] / 255, a[..., 2] / 255
        plant = (h > 20) & (h < 170) & (s > 0.18) & (v > 0.15)  # green / yellow-brown leaf tissue
        return float(plant.mean())

    @staticmethod
    def _describe(cls, conf):
        crop_key, dis_key = cls.split("___")
        name, pathogen, action = INFO.get(dis_key, (dis_key.replace("_", " "), "", ""))
        return {"class": cls, "crop": CROP_NAMES.get(crop_key, crop_key), "disease": name, "pathogen": pathogen,
                "healthy": dis_key == "healthy", "advice": action, "confidence": round(conf, 4)}


disease_model = DiseaseModel()
