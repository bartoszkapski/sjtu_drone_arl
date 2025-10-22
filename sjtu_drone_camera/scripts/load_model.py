#!/usr/bin/env python3

"""
python3 load_model.py ../models/album_frame_4_number_three_v2_finetune/weights/best.pt

python3 load_model.py ../models/album_frame_6_traffic_cone_finetune/weights/best.pt

"""


import argparse
import shutil
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Ustaw bieżący model (.pt) w ../models/current_used_model/current_used_model.pt")
    parser.add_argument("model", help="Ścieżka do pliku modelu .pt")
    args = parser.parse_args()

    src = Path(args.model).expanduser()
    if not src.is_file():
        print(f"[ERR] Brak pliku: {src}", file=sys.stderr)
        sys.exit(2)
    if src.suffix.lower() != ".pt":
        print(f"[ERR] Oczekiwano pliku .pt, otrzymano: {src.name}", file=sys.stderr)
        sys.exit(2)

    script_dir = Path(__file__).resolve().parent
    target_dir = (script_dir / "../models/current_used_model").resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    # Usuń wszystko z katalogu docelowego, aby został tylko jeden model
    for p in target_dir.iterdir():
        try:
            if p.is_file() or p.is_symlink():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(p)
        except Exception as e:
            print(f"[WARN] Nie można usunąć {p}: {e}", file=sys.stderr)

    dst = target_dir / "current_used_model.pt"
    tmp = target_dir / ".current_used_model.pt.tmp"

    # Kopia atomowa: najpierw do pliku tymczasowego, potem rename
    shutil.copy2(src, tmp)
    tmp.replace(dst)

    print(f"Skopiowano: {src} -> {dst}")

if __name__ == "__main__":
    main()