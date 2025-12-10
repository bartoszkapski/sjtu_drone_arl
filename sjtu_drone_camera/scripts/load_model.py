#!/usr/bin/env python3

"""
python3 load_model.py ../models/album_frame_4_number_three_v2_finetune/weights/best.pt

python3 load_model.py ../models/album_human_human_finetune/weights/best.pt

"""


import argparse
import shutil
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Wybór aktualnego modelu")
    parser.add_argument("model")
    args = parser.parse_args()

    src = Path(args.model).expanduser()
    if not src.is_file() or src.suffix.lower() != ".pt":
        print(f"Brak pliku: {src}", file=sys.stderr)
        return

    script_dir = Path(__file__).resolve().parent
    target_dir = (script_dir / "../models/current_used_model").resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    for p in target_dir.iterdir():
        try:
            if p.is_file() or p.is_symlink():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(p)
        except Exception as e:
            pass

    dst = target_dir / "current_used_model.pt"
    tmp = target_dir / ".current_used_model.pt.tmp"

    shutil.copy2(src, tmp)
    tmp.replace(dst)

    print(f"Wybrano aktualny model: {src} --> {dst}")

if __name__ == "__main__":
    main()