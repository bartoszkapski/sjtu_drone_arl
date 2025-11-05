"""
python3 test_model.py --weights ../models/album_human_human_finetune/weights/best.pt --source ../albums/album_human/val/images
"""


import argparse
from pathlib import Path
import numpy as np
import cv2
from ultralytics import YOLO


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--weights", required=True, help="Ścieżka do best.pt")
    p.add_argument("--source", required=True, help="Obraz/katalog/wideo (np. ../albums/album_x/val/images)")
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--device", default="cpu")  # 'cpu' lub '0'
    p.add_argument("--save-vis", default="false", choices=["true","false"])
    p.add_argument("--project", default="../models", help="Gdzie zapisać wizualizacje, jeśli save-vis=true")
    p.add_argument("--name", default="infer", help="Nazwa folderu z wynikami")
    p.add_argument("--class-name", default="", help="Opcjonalny filtr po nazwie klasy")
    args = p.parse_args()

    save_vis = (args.save_vis == "true")

    model = YOLO(args.weights)

    cls_filter = None
    if args.class_name:
        names = model.names if isinstance(model.names, dict) else {i: n for i, n in enumerate(model.names)}
        inv = {v: k for k, v in names.items()}
        if args.class_name in inv:
            cls_filter = [inv[args.class_name]]
        else:
            print(f"Brak klasy '{args.class_name}'. Dostępne: {list(names.values())}")



    results = model.predict(
        source=args.source,
        imgsz=args.imgsz,
        conf=args.conf,
        device=args.device,
        save=save_vis,
        project=str(Path(__file__).parent / args.project),
        name=args.name,
        exist_ok=True,
        verbose=False,
        classes=cls_filter,
    )

    # Programowy dostęp do detekcji
    for i, r in enumerate(results):
        h, w = r.orig_shape
        names = r.names  # mapowanie id->nazwa klasy
        boxes = r.boxes  # ultralytics.engine.results.Boxes
        n = 0 if boxes is None else boxes.shape[0]
        print(f"[{i}] detections: {n}")
        if n:
            xyxy = boxes.xyxy.cpu().numpy()          # (N,4) [x1,y1,x2,y2] w pikselach
            conf = boxes.conf.cpu().numpy()          # (N,)
            cls  = boxes.cls.long().cpu().numpy()    # (N,)
            for j in range(n):
                x1, y1, x2, y2 = xyxy[j].tolist()
                c = float(conf[j])
                k = int(cls[j])
                # YOLO (cx,cy,w,h) znormalizowane:
                cx = ((x1 + x2) / 2.0) / w
                cy = ((y1 + y2) / 2.0) / h
                ww = (x2 - x1) / w
                hh = (y2 - y1) / h
                print(f"  - cls={k}({names.get(k, str(k))}) conf={c:.3f} xyxy=({x1:.1f},{y1:.1f},{x2:.1f},{y2:.1f}) yolo=({cx:.4f},{cy:.4f},{ww:.4f},{hh:.4f})")

        # Jeśli chcesz dostać obraz z narysowanymi bboxami bez zapisu na dysk:
        if not save_vis:
            vis_bgr = r.plot()  # numpy BGR
            # np. podgląd okienkiem (jeśli masz GUI):
            cv2.imshow("pred", vis_bgr); cv2.waitKey(0)
            # lub zapisz ręcznie:
            # cv2.imwrite(str(Path(args.project)/args.name/f"frame_{i:05d}.jpg"), vis_bgr)



if __name__ == "__main__":
    main()