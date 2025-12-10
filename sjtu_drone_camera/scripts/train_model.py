#!/usr/bin/env python3
"""
python3 train_model.py --album ../albums/album_frame_1 --class-name human --epochs 20 --batch 4
"""


import os
import argparse
from pathlib import Path
import shutil

from ultralytics import YOLO
from ultralytics.utils import SETTINGS


def make_data_yaml(album_dir: Path, class_name: str, out_dir: Path, dummies_dir: Path = None) -> Path:
    album_dir = album_dir.resolve()
    train_images = album_dir / "train" / "images"
    val_images = album_dir / "val" / "images"
    assert train_images.is_dir(), f"Missing: {train_images}"
    assert val_images.is_dir(), f"Missing: {val_images}"
    
    out_dir.mkdir(parents=True, exist_ok=True)
    

    if dummies_dir and dummies_dir.exists():
        staged_train = _merge_train_with_dummies(train_images, album_dir / "train" / "labels", 
                                                   dummies_dir, out_dir)
        train_path = str(staged_train)
    else:
        train_path = str(train_images)
    
    data_yaml = out_dir / f"data_{album_dir.name}.yaml"
    data_yaml.write_text(
        "train: {}\nval: {}\n\n# one-class dataset\nnames: ['{}']\n".format(
            train_path, str(val_images), class_name
        ),
        encoding="utf-8",
    )
    return data_yaml


def _merge_train_with_dummies(train_images: Path, train_labels: Path, dummies_dir: Path, out_dir: Path) -> Path:
    # train + dummies
    staged = out_dir / "staged_train_with_dummies"
    staged_images = staged / "images"
    staged_labels = staged / "labels"

    if staged.exists():
        shutil.rmtree(staged)

    staged_images.mkdir(parents=True, exist_ok=True)
    staged_labels.mkdir(parents=True, exist_ok=True)
    
    for img in train_images.glob("*.[jJ][pP][gG]"):
        (staged_images / img.name).symlink_to(img)
    for img in train_images.glob("*.[pP][nN][gG]"):
        (staged_images / img.name).symlink_to(img)
    
    for lbl in train_labels.glob("*.txt"):
        shutil.copy2(lbl, staged_labels / lbl.name)
    
    dummies_images = dummies_dir / "images"
    dummies_labels = dummies_dir / "labels"
    
    if dummies_images.exists():
        for img in dummies_images.glob("*.[jJ][pP][gG]"):
            (staged_images / img.name).symlink_to(img)
        for img in dummies_images.glob("*.[pP][nN][gG]"):
            (staged_images / img.name).symlink_to(img)
    
    if dummies_labels.exists():
        for lbl in dummies_labels.glob("*.txt"):
            # pusty plik label.txt = brak obiektu
            shutil.copy2(lbl, staged_labels / lbl.name)
    
    return staged_images


def make_data_yaml_multi(train_images: Path, val_images: Path, names: list[str], out_dir: Path, album_name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    data_yaml = out_dir / f"data_{album_name}_multi.yaml"
    data_yaml.write_text(
        "train: {}\nval: {}\n\nnames: {}\n".format(str(train_images), str(val_images), names),
        encoding="utf-8",
    )
    return data_yaml


def main_tune_single_class():
    parser = argparse.ArgumentParser(description="Uczenie pre-trenowanego mdoelu YOLO11n")
    parser.add_argument("--album", required=True, type=str)
    parser.add_argument("--models-dir", default="../models", type=str)
    parser.add_argument("--model", default="yolo11n.pt", type=str)
    parser.add_argument("--class-name", default="object", type=str)
    parser.add_argument("--epochs", default=50, type=int)
    parser.add_argument("--batch", default=16, type=int)
    parser.add_argument("--workers", default=2, type=int)
    parser.add_argument("--device", default="cpu", type=str)
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    album_dir = (script_dir / args.album).resolve() if not os.path.isabs(args.album) else Path(args.album)
    models_dir = (script_dir / args.models_dir).resolve() if not os.path.isabs(args.models_dir) else Path(args.models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    # dummies
    dummies_dir = (script_dir / "../albums/dummies").resolve()
    if not dummies_dir.exists():
        (dummies_dir / "images").mkdir(parents=True, exist_ok=True)
        (dummies_dir / "labels").mkdir(parents=True, exist_ok=True)

    SETTINGS.update(weights_dir=str(models_dir))
    SETTINGS.update(runs_dir=str(models_dir))

    data_yaml = make_data_yaml(album_dir, args.class_name, models_dir, dummies_dir)

    model = YOLO(args.model)

    run_name = f"{album_dir.name}_{args.class_name}_finetune"
    results = model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        batch=args.batch,
        workers=args.workers,
        device=args.device,
        project=str(models_dir),
        name=run_name,
        exist_ok=True,
        pretrained=True,
        verbose=True,
    )

    print(f"Base weights dir: {models_dir}")
    print(f"Run dir: {models_dir / run_name}")
    print(f"Best weights: {models_dir / run_name / 'weights' / 'best.pt'}")



if __name__ == "__main__":
    main_tune_single_class()
