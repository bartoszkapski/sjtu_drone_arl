#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

from cv_bridge import CvBridge
import cv2
from ultralytics import YOLO

import time



class DetectObjectByYolo(Node):
    def __init__(self):
        super().__init__('detect_object_by_yolo')
        self.sub = self.create_subscription(Image, '/simple_drone/bottom/image_raw', self.callback_read_image, 10)
        self.pub = self.create_publisher(Image, '/simple_drone/bottom/image_object_detection', 10)
        self.bridge = CvBridge()

        self.declare_parameter('target_class_name', '')
        self.target_class_name = self.get_parameter('target_class_name').get_parameter_value().string_value

        self.get_logger().info("Loading model...")

        self.weights_path = "/home/fhtw_user/sim_ws/src/sjtu_drone_camera/models/current_used_model/current_used_model.pt"
        self.model = YOLO(self.weights_path)
        self.imgsz = 640
        self.conf = 0.25

        self.classes = self._resolve_target_class_indices()
        if self.classes is None:
            self.get_logger().warn("Brak filtra klas (będzie wykrywać wszystkie). Ustaw param target_class_name, aby filtrować jedną klasę.")
        else:
            self.get_logger().info(f"Filtrovaną klasą jest: idx={self.classes[0]} name='{self.model.names[self.classes[0]]}'")

        self._busy = False 

        # Wypisz listę klas dostępnych w modelu (ułatwia znalezienie poprawnej nazwy)
        try:
            names_str = ", ".join([f"{i}:{n}" for i, n in (self.model.names.items() if isinstance(self.model.names, dict) else enumerate(self.model.names))])
            self.get_logger().info(f"Model classes: {names_str}")
        except Exception:
            pass


        self.get_logger().info("DetectObjectByYolo started")
        

    def _resolve_target_class_indices(self):
        """
        Zwraca [idx] dla target_class_name, albo:
        - [0] jeśli model jest jednoklasowy i nie podano nazwy
        - None jeśli nie znaleziono nazwy i model ma wiele klas (brak filtrowania)
        """
        names = self.model.names
        # Ujednolić do dict[int]->str
        if not isinstance(names, dict):
            names = {i: n for i, n in enumerate(names)}

        if self.target_class_name:
            for i, n in names.items():
                if n == self.target_class_name:
                    return [int(i)]
            self.get_logger().warn(f"Nie znaleziono klasy '{self.target_class_name}' w modelu. Dostępne: {list(names.values())}")
            return None

        # Brak podanej nazwy: jeśli model ma 1 klasę, filtruj ją; jeśli więcej, nie filtruj.
        if len(names) == 1:
            only_idx = int(next(iter(names.keys())))
            return [only_idx]
        return None


    def callback_read_image(self, msg: Image):
        if self._busy:
            return
        self._busy = True
        try:
            cv_bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

            # Inference na pojedynczej klatce (numpy BGR)
            results = self.model.predict(
                source=cv_bgr,
                imgsz=self.imgsz,
                conf=self.conf,
                classes=self.classes,
                device="cpu",
                save=False,
                verbose=False,
            )

            # Annotacja i publikacja
            vis_bgr = results[0].plot()  # BGR numpy z narysowanymi bboxami
            out_msg = self.bridge.cv2_to_imgmsg(vis_bgr, encoding='bgr8')
            out_msg.header = msg.header  # zachowaj timestamp/frame_id
            self.pub.publish(out_msg)

        except Exception as e:
            self.get_logger().error(f"inference error: {e}")
        finally:
            self._busy = False






def main():
        rclpy.init()
        node = DetectObjectByYolo()
        try:
            rclpy.spin(node)
        except KeyboardInterrupt:
            pass
        finally:
            node.destroy_node()
            rclpy.shutdown()

if __name__ == "__main__":
    main()
