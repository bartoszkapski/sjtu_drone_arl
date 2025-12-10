#!/usr/bin/env python3
"""
python3 test_model.py --weights ../models/album_frame_1_human_finetune/weights/best.pt --source ../albums/album_frame_1/val/images
"""


import argparse
from pathlib import Path
import numpy as np
import cv2
from ultralytics import YOLO


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--weights", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--device", default="cpu")
    p.add_argument("--save-vis", default="false", choices=["true","false"])
    p.add_argument("--project", default="../models")
    p.add_argument("--name", default="infer")
    p.add_argument("--class-name", default="")
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
            print(f"Brak klasy '{args.class_name}'\n dostępne: {list(names.values())}")



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


    for i, r in enumerate(results):
        h, w = r.orig_shape
        names = r.names
        boxes = r.boxes
        n = 0 if boxes is None else boxes.shape[0]
        print(f"[{i}] detections: {n}")
        if n:
            xyxy = boxes.xyxy.cpu().numpy()          # (N,4) [x1,y1,x2,y2]
            conf = boxes.conf.cpu().numpy()          # (N,)
            cls  = boxes.cls.long().cpu().numpy()    # (N,)
            for j in range(n):
                x1, y1, x2, y2 = xyxy[j].tolist()
                c = float(conf[j])
                k = int(cls[j])

                #(cx,cy,w,h):
                cx = ((x1 + x2) / 2.0) / w
                cy = ((y1 + y2) / 2.0) / h
                ww = (x2 - x1) / w
                hh = (y2 - y1) / h
                print(f"  - cls={k}({names.get(k, str(k))}) conf={c:.3f} xyxy=({x1:.1f},{y1:.1f},{x2:.1f},{y2:.1f}) yolo=({cx:.4f},{cy:.4f},{ww:.4f},{hh:.4f})")

        if not save_vis:
            vis_bgr = r.plot()  # BGR
            cv2.imshow("pred", vis_bgr); cv2.waitKey(0)



if __name__ == "__main__":
    main()