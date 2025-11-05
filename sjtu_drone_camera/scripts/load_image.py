"""
python3 load_image.py --image ../target_images/frame_5.jpg --bbox false
"""


import argparse
import os
import random
from typing import List, Tuple, Optional
from pathlib import Path
import math

import numpy as np
import cv2

import torch
import torch.nn as nn
from torchvision import transforms as _T
from torchvision.transforms import v2
from torchvision import tv_tensors
from torchvision.transforms.functional import InterpolationMode

from cv2utilities import SelectRectange



def to_yolo_xywh_norm(bbox: Tuple[float, float, float, float],
                      img_w: int,
                      img_h: int,
                      fmt: str = "xywh") -> Tuple[float, float, float, float]:
    """
    Convert bbox to YOLO normalized (cx, cy, w, h).
    fmt: 'xywh' -> (x, y, w, h) top-left
         'xyxy' -> (x1, y1, x2, y2)
    """
    if fmt == "xyxy":
        x1, y1, x2, y2 = bbox
        x, y, w, h = x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1)
    else:
        x, y, w, h = bbox

    cx = (x + w / 2.0) / float(img_w)
    cy = (y + h / 2.0) / float(img_h)
    nw = w / float(img_w)
    nh = h / float(img_h)

    cx = min(max(cx, 0.0), 1.0)
    cy = min(max(cy, 0.0), 1.0)
    nw = min(max(nw, 0.0), 1.0)
    nh = min(max(nh, 0.0), 1.0)
    return (cx, cy, nw, nh)


########################################################################################


def yolo_to_xyxy_pixels(yolo_box: Tuple[float, float, float, float], img_w: int, img_h: int) -> torch.Tensor:
    cx, cy, w, h = yolo_box
    x1 = (cx - w / 2.0) * img_w
    y1 = (cy - h / 2.0) * img_h
    x2 = (cx + w / 2.0) * img_w
    y2 = (cy + h / 2.0) * img_h
    box = torch.tensor([x1, y1, x2, y2], dtype=torch.float32)
    # klip do granic obrazu
    box[0::2] = box[0::2].clamp(0, img_w - 1e-3)
    box[1::2] = box[1::2].clamp(0, img_h - 1e-3)
    return box

def xyxy_pixels_to_yolo(box_xyxy: torch.Tensor, img_w: int, img_h: int) -> Tuple[float, float, float, float]:
    x1, y1, x2, y2 = box_xyxy.tolist()
    w = (x2 - x1) / img_w
    h = (y2 - y1) / img_h
    cx = (x1 + x2) / 2.0 / img_w
    cy = (y1 + y2) / 2.0 / img_h
    return (float(cx), float(cy), float(w), float(h))

# ======= Własne transformatory (torch) =======

class RandomApplyModule(nn.Module):
    def __init__(self, module: nn.Module, p: float):
        super().__init__()
        self.module = module
        self.p = p
    def forward(self, sample):
        if torch.rand(()) < self.p:
            return self.module(sample)
        return sample

class RandomRGBShift(nn.Module):
    """
    Przesuwa składowe R,G,B o losowe wartości w [-shift, shift].
    """
    def __init__(self, max_shift: int = 20, p: float = 0.2):
        super().__init__()
        self.max_shift = int(max_shift)
        self.p = p
    def forward(self, sample):
        if torch.rand(()) >= self.p:
            return sample
        img = sample["image"]  # tv_tensors.Image, uint8 [C,H,W], RGB
        # losowe przesunięcie per kanał
        shifts = torch.randint(low=-self.max_shift, high=self.max_shift + 1, size=(3,), dtype=torch.int16)
        out = img.to(torch.int16)
        out[0] = (out[0] + shifts[0]).clamp(0, 255)
        out[1] = (out[1] + shifts[1]).clamp(0, 255)
        out[2] = (out[2] + shifts[2]).clamp(0, 255)
        sample["image"] = tv_tensors.Image(out.to(torch.uint8))
        return sample

class AdditiveGaussianNoise(nn.Module):
    """
    Dodaje szum Gaussa o sigma ~ U(sigma_min, sigma_max) (na skali 0-255).
    """
    def __init__(self, sigma_min: float = 5.0, sigma_max: float = 30.0, p: float = 0.2):
        super().__init__()
        self.sigma_min = float(sigma_min)
        self.sigma_max = float(sigma_max)
        self.p = p
    def forward(self, sample):
        if torch.rand(()) >= self.p:
            return sample
        img = sample["image"]  # uint8 RGB [C,H,W]
        sigma = torch.empty(()).uniform_(self.sigma_min, self.sigma_max).item()
        noise = torch.randn_like(img, dtype=torch.float32) * sigma
        out = img.to(torch.float32) + noise
        out = out.clamp(0, 255).to(torch.uint8)
        sample["image"] = tv_tensors.Image(out)
        return sample

class RandomMotionBlur(nn.Module):
    """
    Prosty liniowy motion blur o losowej długości i kącie.
    """
    def __init__(self, max_ksize: int = 5, p: float = 0.2):
        super().__init__()
        if max_ksize % 2 == 0:
            max_ksize += 1
        self.max_ksize = max_ksize
        self.p = p
    def _kernel(self, k: int, angle_rad: float) -> torch.Tensor:
        # generuj liniowe jądro k x k obrócone o angle_rad
        center = (k - 1) / 2.0
        y, x = torch.meshgrid(torch.arange(k), torch.arange(k), indexing="ij")
        x = x - center
        y = y - center
        # rzut na kierunek ruchu
        dirx, diry = math.cos(angle_rad), math.sin(angle_rad)
        proj = x * dirx + y * diry
        ker = (proj.abs() < 0.5).float()  # wąska linia
        ker = ker / ker.sum().clamp_min(1.0)
        return ker
    def forward(self, sample):
        if torch.rand(()) >= self.p:
            return sample
        img = sample["image"]  # uint8 [C,H,W]
        k = int(torch.randint(3, self.max_ksize + 1, (1,)).item())
        if k % 2 == 0:
            k += 1
        angle = float(torch.rand(()) * 2 * math.pi)
        k2d = self._kernel(k, angle).to(dtype=torch.float32, device=img.device)
        # konwolucja per kanał
        img_f = img.to(torch.float32).unsqueeze(0)  # [1,C,H,W]
        k2d = k2d.expand(img_f.shape[1], 1, k, k)   # [C,1,k,k]
        out = torch.nn.functional.conv2d(img_f, k2d, padding=k//2, groups=img_f.shape[1])
        out = out.squeeze(0).clamp(0, 255).to(torch.uint8)
        sample["image"] = tv_tensors.Image(out)
        return sample

class ResizeLongestMax(nn.Module):
    """
    Skaluje tak, aby dłuższy bok == max_size (z zachowaniem proporcji).
    """
    def __init__(self, max_size: int, interpolation=InterpolationMode.BILINEAR):
        super().__init__()
        self.max_size = int(max_size)
        self.interp = interpolation
    def forward(self, sample):
        img: tv_tensors.Image = sample["image"]
        _, h, w = img.shape
        if max(h, w) == self.max_size:
            return sample
        scale = self.max_size / float(max(h, w))
        new_h, new_w = int(round(h * scale)), int(round(w * scale))
        resize = v2.Resize(size=(new_h, new_w), interpolation=self.interp, antialias=True)
        # torchvision v2 obsługuje dict z boxes/labels
        return resize(sample)

class PadToSquare(nn.Module):
    """
    Dolewa piksele do kwadratu (img_size x img_size) kolorem 114.
    """
    def __init__(self, size: int, fill: Tuple[int, int, int] = (114, 114, 114)):
        super().__init__()
        self.size = int(size)
        self.fill = fill
    def forward(self, sample):
        img: tv_tensors.Image = sample["image"]
        _, h, w = img.shape
        pad_h = self.size - h
        pad_w = self.size - w
        top = 0
        left = 0
        pad = (left, 0, pad_w, pad_h)  # (left, top, right, bottom)
        return v2.Pad(padding=pad, fill=self.fill)(sample)

def _random_perspective_module(fill=(114,114,114)):
    # Albumentations: scale (0.02, 0.05) -> w torchvision użyjemy losowego distortion_scale
    distortion_scale = float(torch.empty(()).uniform_(0.02, 0.05))
    return v2.RandomPerspective(distortion_scale=distortion_scale, interpolation=InterpolationMode.BILINEAR, fill=fill)

# ======= Główna budowa transformacji =======

def build_torchvision_transform(has_labels: bool, img_size: Optional[int] = None, seed: Optional[int] = None) -> nn.Module:
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)

    tfms: List[nn.Module] = [
        v2.RandomHorizontalFlip(p=0.5),
        v2.ColorJitter(brightness=0.2, contrast=0.2),          # ~ RandomBrightnessContrast(p=0.5)
        RandomApplyModule(v2.ColorJitter(saturation=0.4, hue=0.1), p=0.4),  # ~ HueSaturationValue(p=0.4)
        RandomRGBShift(max_shift=20, p=0.2),                   # ~ RGBShift(p=0.2)
        AdditiveGaussianNoise(5.0, 30.0, p=0.2),               # ~ GaussNoise
        RandomMotionBlur(max_ksize=5, p=0.2),                  # ~ MotionBlur
        RandomApplyModule(
            v2.RandomAffine(
                degrees=15,
                translate=(0.06, 0.06),
                scale=(0.8, 1.2),
                interpolation=InterpolationMode.BILINEAR,
                fill=114
            ),
            p=0.7
        ),
        RandomApplyModule(_T.Lambda(lambda s: _random_perspective_module(fill=(114,114,114))(s)), p=0.15),
    ]

    if img_size:
        tfms += [
            ResizeLongestMax(img_size, interpolation=InterpolationMode.BILINEAR),
            PadToSquare(img_size, fill=(114,114,114)),
        ]

    pipeline = v2.Compose(tfms)
    return pipeline

# ======= Generator albumu z jednego obrazu + 1 bbox YOLO =======

def generate_album_from_single_image(
    image_path: str,
    yolo_bbox: Tuple[float, float, float, float],
    class_id: int = 0,
    img_size: Optional[int] = 640,
    n_train: int = 100,
    n_val: int = 20,
    seed: Optional[int] = 0,
) -> Path:
    """
    Tworzy album w ../albums/album_<nazwa_pliku_bez_ext>/{train,val}/{images,labels}
    Zapisuje .jpg i .txt (YOLO). Filtruje pudełka o małym rozmiarze (<16 px^2).
    """
    rng = random.Random(seed if seed is not None else 0)
    torch.manual_seed(seed if seed is not None else 0)
    np.random.seed(seed if seed is not None else 0)

    image_path = Path(image_path).resolve()
    assert image_path.is_file(), f"Brak obrazu: {image_path}"
    stem = image_path.stem
    out_root = (Path(__file__).resolve().parent / "../albums" / f"album_{stem}").resolve()

    for split in ("train", "val"):
        (out_root / split / "images").mkdir(parents=True, exist_ok=True)
        (out_root / split / "labels").mkdir(parents=True, exist_ok=True)

    # wczytaj obraz jako RGB uint8 tensor [C,H,W]
    import cv2
    bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise RuntimeError(f"Nie można wczytać obrazu: {image_path}")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    H, W = rgb.shape[:2]
    img_t = torch.from_numpy(rgb).permute(2, 0, 1).contiguous()  # [C,H,W], uint8
    image_tv = tv_tensors.Image(img_t)

    # bbox jako XYXY (px)
    box_xyxy = yolo_to_xyxy_pixels(yolo_bbox, W, H).unsqueeze(0)  # [1,4]
    boxes_tv = tv_tensors.BoundingBoxes(box_xyxy, format=tv_tensors.BoundingBoxFormat.XYXY, canvas_size=(H, W))
    labels = torch.tensor([class_id], dtype=torch.int64)

    tfm = build_torchvision_transform(has_labels=True, img_size=img_size, seed=seed)

    def save_sample(idx: int, split: str):
        # Losowy seed per próbka (dla różnorodności i powtarzalności)
        s = (seed if seed is not None else 0) + idx + (0 if split == "train" else 10_000)
        random.seed(s); np.random.seed(s); torch.manual_seed(s)

        sample = {"image": image_tv.clone(), "boxes": boxes_tv.clone(), "labels": labels.clone()}
        out = tfm(sample)

        out_img: torch.Tensor = out["image"]  # [C,H,W] uint8
        out_boxes: tv_tensors.BoundingBoxes = out["boxes"]
        out_labels: torch.Tensor = out["labels"]

        h2, w2 = out_img.shape[-2], out_img.shape[-1]
        # filtracja: usuń bardzo małe lub niepoprawne boxy
        valid_boxes = []
        valid_labels = []
        for b, lab in zip(out_boxes, out_labels):
            x1, y1, x2, y2 = b.tolist()
            w = max(0.0, x2 - x1)
            h = max(0.0, y2 - y1)
            area = w * h
            if w >= 1.0 and h >= 1.0 and area >= 16.0:
                valid_boxes.append([x1, y1, x2, y2])
                valid_labels.append(int(lab))

        # zapis obrazu
        out_rgb = out_img.permute(1, 2, 0).cpu().numpy()
        out_bgr = out_rgb[:, :, ::-1]
        img_name = f"{stem}_{split}_{idx:05d}.jpg"
        lbl_name = img_name.replace(".jpg", ".txt")
        cv2.imwrite(str(out_root / split / "images" / img_name), out_bgr)

        # zapis etykiet YOLO
        with open(out_root / split / "labels" / lbl_name, "w", encoding="utf-8") as f:
            for b, lab in zip(valid_boxes, valid_labels):
                cx, cy, ww, hh = xyxy_pixels_to_yolo(torch.tensor(b, dtype=torch.float32), w2, h2)
                # klip do [0,1]
                cx = min(max(cx, 0.0), 1.0)
                cy = min(max(cy, 0.0), 1.0)
                ww = min(max(ww, 0.0), 1.0)
                hh = min(max(hh, 0.0), 1.0)
                f.write(f"{lab} {cx:.6f} {cy:.6f} {ww:.6f} {hh:.6f}\n")

    for i in range(n_train):
        save_sample(i, "train")
    for i in range(n_val):
        save_sample(i, "val")

    return out_root


########################################################################################


def main():
    parser = argparse.ArgumentParser(description="Load image and select bounding box.")
    parser.add_argument("--image", required=True, type=str, help="path to target image.")
    parser.add_argument("--bbox", default="false", choices=["true","false"], help="does the bbox file already exist? (true/false)")

    args = parser.parse_args()

    if not os.path.isfile(args.image):
        print(f"[ERR] Brak pliku obrazu: {args.image}")
        raise SystemExit(2)
    
    image = cv2.imread(args.image, cv2.IMREAD_COLOR)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    bbox = None
    if args.bbox == "true":
        print('przyszłe odczytanie bbox')
    else:
        select_bbox = SelectRectange(image[...,::-1])
        bbox , _ = select_bbox.select_and_get_rect()

    print(f"Selected bbox: {bbox}")

    img_h, img_w = image.shape[:2]
    cx, cy, w, h = to_yolo_xywh_norm(tuple(map(float, bbox)), img_w, img_h, fmt="xywh")
    class_id = 0  # Twoja nowa klasa
    label_line = f"{class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"
    print("YOLO label:", label_line)


    # Wygeneruj album z jednego obrazu + bbox (YOLO cx,cy,w,h)
    out_dir = generate_album_from_single_image(
        image_path=args.image,
        yolo_bbox=(cx, cy, w, h),
        class_id=class_id,
        img_size=640,     # zmień jeśli chcesz inny rozmiar wejścia
        n_train=60,      # liczba próbek treningowych
        n_val=10,         # liczba próbek walidacyjnych
        seed=42,
    )
    print(f"Album zapisany w: {out_dir}")





if __name__ == "__main__":
    main()



