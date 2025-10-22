"""
python3 train_model.py --album ../albums/album_frame_4 --class-name number_three_v2 --epochs 10 --batch 4

python3 train_model.py --album ../albums/album_frame_6 --class-name traffic_cone --epochs 20 --batch 4 --keep-base-classes --lr0 1e-4
"""


import os
import argparse
from pathlib import Path
import shutil

from ultralytics import YOLO
from ultralytics.utils import SETTINGS


def make_data_yaml(album_dir: Path, class_name: str, out_dir: Path) -> Path:
    album_dir = album_dir.resolve()
    train_images = album_dir / "train" / "images"
    val_images = album_dir / "val" / "images"
    assert train_images.is_dir(), f"Missing: {train_images}"
    assert val_images.is_dir(), f"Missing: {val_images}"
    out_dir.mkdir(parents=True, exist_ok=True)
    data_yaml = out_dir / f"data_{album_dir.name}.yaml"
    data_yaml.write_text(
        "train: {}\nval: {}\n\n# one-class dataset\nnames: ['{}']\n".format(
            str(train_images), str(val_images), class_name
        ),
        encoding="utf-8",
    )
    return data_yaml



def _model_names_list(model) -> list[str]:
    names = model.names
    if isinstance(names, dict):
        return [names[i] for i in sorted(names.keys())]
    return list(names)



def _stage_album_with_new_index(album_dir: Path, out_root: Path, new_idx: int) -> Path:
    """
    Tworzy kopię struktury datasetu ze zlinkowanymi obrazami i etykietami przemapowanymi na new_idx.
    Zwraca ścieżkę do katalogu staging (z podfolderami train/ i val/).
    """
    staged = out_root / f"{album_dir.name}_staged_cls_{new_idx}"
    for split in ["train", "val"]:
        src_img = album_dir / split / "images"
        src_lbl = album_dir / split / "labels"
        assert src_img.is_dir(), f"Missing: {src_img}"
        assert src_lbl.is_dir(), f"Missing: {src_lbl}"

        dst_img = staged / split / "images"
        dst_lbl = staged / split / "labels"
        dst_img.mkdir(parents=True, exist_ok=True)
        dst_lbl.mkdir(parents=True, exist_ok=True)

        # linkujemy obrazy (szybko i bez kopiowania)
        if not dst_img.exists():
            dst_img.mkdir(parents=True, exist_ok=True)
        # utwórz symlink folderu obrazów
        # jeśli symlink już istnieje, pomiń
        try:
            if not dst_img.is_symlink():
                # czyści pusty katalog docelowy i tworzy symlink
                for p in dst_img.iterdir():
                    p.unlink()
                dst_img.rmdir()
                os.symlink(src_img, dst_img, target_is_directory=True)
        except FileExistsError:
            pass

        # przemapowanie etykiet: pierwszy token w każdej linii -> new_idx
        for lbl_file in src_lbl.glob("*.txt"):
            out_file = dst_lbl / lbl_file.name
            lines = lbl_file.read_text(encoding="utf-8").splitlines()
            remapped = []
            for ln in lines:
                if not ln.strip():
                    continue
                parts = ln.split()
                parts[0] = str(new_idx)
                remapped.append(" ".join(parts))
            out_file.write_text("\n".join(remapped) + ("\n" if remapped else ""), encoding="utf-8")
    return staged

def make_data_yaml_multi(train_images: Path, val_images: Path, names: list[str], out_dir: Path, album_name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    data_yaml = out_dir / f"data_{album_name}_multi.yaml"
    data_yaml.write_text(
        "train: {}\nval: {}\n\nnames: {}\n".format(str(train_images), str(val_images), names),
        encoding="utf-8",
    )
    return data_yaml




def main_tune_single_class():
    parser = argparse.ArgumentParser(description="Fine-tune YOLO11 on a single-class album.")
    parser.add_argument("--album", required=True, type=str, help="Path to album dir (e.g. ../albums/album_frame_3)")
    parser.add_argument("--models-dir", default="../models", type=str, help="Where to store models and runs")
    parser.add_argument("--model", default="yolo11n.pt", type=str, help="Base model (yolo11n.pt is the light one)")
    parser.add_argument("--class-name", default="object", type=str, help="Single class name")
    parser.add_argument("--epochs", default=50, type=int)
    parser.add_argument("--batch", default=16, type=int)
    parser.add_argument("--workers", default=2, type=int)
    parser.add_argument("--device", default="cpu", type=str)  # 'cpu' or '0' for GPU if available
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    album_dir = (script_dir / args.album).resolve() if not os.path.isabs(args.album) else Path(args.album)
    models_dir = (script_dir / args.models_dir).resolve() if not os.path.isabs(args.models_dir) else Path(args.models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    # Put both weights and runs into ../models so originals and outputs land there
    SETTINGS.update(weights_dir=str(models_dir))
    SETTINGS.update(runs_dir=str(models_dir))

    # Create data.yaml pointing to album train/val
    data_yaml = make_data_yaml(album_dir, args.class_name, models_dir)

    # Load (download if needed) the base model into models_dir
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




def main_fine_tune():
    parser = argparse.ArgumentParser(description="Fine-tune YOLO11 on a single-class album.")
    parser.add_argument("--album", required=True, type=str, help="Path to album dir (e.g. ../albums/album_frame_3)")
    parser.add_argument("--models-dir", default="../models", type=str, help="Where to store models and runs")
    parser.add_argument("--model", default="yolo11n.pt", type=str, help="Base model (yolo11n.pt is the light one)")
    parser.add_argument("--class-name", default="object", type=str, help="Single class name")
    parser.add_argument("--epochs", default=50, type=int)
    parser.add_argument("--batch", default=16, type=int)
    parser.add_argument("--workers", default=2, type=int)
    parser.add_argument("--device", default="cpu", type=str)  # 'cpu' or '0' for GPU if available
    parser.add_argument("--keep-base-classes", action="store_true",
                        help="Zachowaj klasy modelu bazowego i dodaj nową klasę (bez redukcji do 1 klasy).")
    parser.add_argument("--lr0", type=float, default=None, help="Początkowy learning rate (opcjonalnie nadpisz).")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    album_dir = (script_dir / args.album).resolve() if not os.path.isabs(args.album) else Path(args.album)
    models_dir = (script_dir / args.models_dir).resolve() if not os.path.isabs(args.models_dir) else Path(args.models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    # Put both weights and runs into ../models so originals and outputs land there
    SETTINGS.update(weights_dir=str(models_dir))
    SETTINGS.update(runs_dir=str(models_dir))

    # Load (download if needed) the base model into models_dir
    model = YOLO(args.model)

    if args.keep_base_classes:
        base_names = _model_names_list(model)  # np. 80 klas COCO
        if args.class_name in base_names:
            names_all = base_names  # klasa już istnieje
            new_idx = base_names.index(args.class_name)
        else:
            names_all = base_names + [args.class_name]
            new_idx = len(names_all) - 1

        # Przygotuj staging dataset z przemapowanymi etykietami na indeks nowej klasy
        staged_dir = _stage_album_with_new_index(album_dir, models_dir, new_idx)
        data_yaml = make_data_yaml_multi(
            staged_dir / "train" / "images",
            staged_dir / "val" / "images",
            names_all,
            models_dir,
            album_dir.name,
        )
    else:
        # Tryb jednoklasowy (obecne zachowanie)
        data_yaml = make_data_yaml(album_dir, args.class_name, models_dir)

    run_name = f"{album_dir.name}_{args.class_name}_finetune"
    train_kwargs = dict(
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

    if args.keep_base_classes:
        # Zamroź backbone, ewentualnie też neck (freeze='backbone' zamraża backbone; wartości liczbowe zamrażają pierwsze N warstw)
        train_kwargs["freeze"] = "backbone"
        # delikatny LR, by minimalnie ruszyć głowicę
        if args.lr0 is not None:
            train_kwargs["lr0"] = args.lr0
        else:
            train_kwargs["lr0"] = 1e-3

    results = model.train(**train_kwargs)

    print(f"Base weights dir: {models_dir}")
    print(f"Run dir: {models_dir / run_name}")
    print(f"Best weights: {models_dir / run_name / 'weights' / 'best.pt'}")




if __name__ == "__main__":
    main_tune_single_class()
    # main_fine_tune()