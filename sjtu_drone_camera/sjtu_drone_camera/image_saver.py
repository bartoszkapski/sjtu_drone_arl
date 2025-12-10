#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import time

"""
ros2 run sjtu_drone_camera image_saver

Zapisuje aktualną klatkę obrazu kamery dolnej do pliku
"""

class ImageSaver(Node):
    def __init__(self):
        super().__init__('image_saver')
        self.sub = self.create_subscription(Image, '/simple_drone/bottom/image_raw', self.callback, 10)
        self.bridge = CvBridge()
        self.saved = False


    def callback(self, msg):
        if not self.saved:
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            file_name = f'frame_{int(time.time())}.jpg'
            cv2.imwrite(file_name, cv_image)
            self.get_logger().info(f'Saved {file_name}')
            self.saved = True



def main(args=None):
    rclpy.init(args=args)
    node = ImageSaver()
    try:
        while rclpy.ok() and not node.saved:
            rclpy.spin_once(node, timeout_sec=0.1)
        print("Zapisano obraz")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
