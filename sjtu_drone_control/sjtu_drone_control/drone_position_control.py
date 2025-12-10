import rclpy
import sys
import argparse
import time
import math
from rclpy import utilities
from geometry_msgs.msg import Twist
from sjtu_drone_control.drone_utils.drone_object import DroneObject
from sjtu_drone_control.drone_utils.controllers import PID


class DronePositionControl(DroneObject):
    def __init__(self, x=None, y=None, z=None):
        super().__init__('drone_position_control')
        self.get_logger().info('Initcjalizacja drona')

        self.pid_x = PID(kp=1.5, ki=0.1, kd=0.5, min_out=-2.0, max_out=2.0)
        self.pid_y = PID(kp=1.5, ki=0.1, kd=0.5, min_out=-2.0, max_out=2.0)
        self.pid_z = PID(kp=2.0, ki=0.1, kd=0.8, min_out=-1.5, max_out=1.5)
        time.sleep(1)
        
        current_x = self.gt_pose.position.x
        current_y = self.gt_pose.position.y
        current_z = self.gt_pose.position.z
        self.get_logger().info(f'Pozycja aktualna: x={current_x:.2f}, y={current_y:.2f}, z={current_z:.2f}')
        
        self.target_x = x if x is not None else current_x
        self.target_y = y if y is not None else current_y
        self.target_z = z if z is not None else current_z
        
        self.get_logger().info(f'Pozycja docelowa:  x={self.target_x:.2f}, y={self.target_y:.2f}, z={self.target_z:.2f}')

        self.posCtrl(False)
        
        # poz control timer
        self.control_timer = self.create_timer(0.05, self.control_loop) 
        self.target_reached = False

    def control_loop(self):
        if self.target_reached:
            return
        
        current_x = self.gt_pose.position.x
        current_y = self.gt_pose.position.y
        current_z = self.gt_pose.position.z
        
        error_x = self.target_x - current_x
        error_y = self.target_y - current_y
        error_z = self.target_z - current_z
        
        distance = math.sqrt(error_x**2 + error_y**2 + error_z**2)
        if distance < 0.2:
            if not self.target_reached:
                self.get_logger().info(f'Cel osiągnięty! Pozycja końcowa: x={current_x:.2f}, y={current_y:.2f}, z={current_z:.2f}')
                self.target_reached = True
                self.publish_zero_velocity()
            return
        
        dt = 0.05  # 50ms
        vel_x = self.pid_x.compute(error_x, dt)
        vel_y = self.pid_y.compute(error_y, dt)
        vel_z = self.pid_z.compute(error_z, dt)
        
        cmd = Twist()
        cmd.linear.x = vel_x
        cmd.linear.y = vel_y
        cmd.linear.z = vel_z
        cmd.angular.x = 0.0
        cmd.angular.y = 0.0
        cmd.angular.z = 0.0
        
        self.pubCmd.publish(cmd)
        
    
    def publish_zero_velocity(self):
        cmd = Twist()
        self.pubCmd.publish(cmd)


def main(args=None):
    rclpy.init(args=args)
    
    args = utilities.remove_ros_args(sys.argv[1:])
    parser = argparse.ArgumentParser(description='Drone Position Control - assumes drone is already flying (takeoff done externally)')
    parser.add_argument('--x', type=float, default=None, help='Target X position in meters (default: keep current)')
    parser.add_argument('--y', type=float, default=None, help='Target Y position in meters (default: keep current)')
    parser.add_argument('--z', type=float, default=None, help='Target Z position/height in meters (default: keep current)')
    parsed_args = parser.parse_args(args)
    
    drone_position_control_node = DronePositionControl(x=parsed_args.x,y=parsed_args.y,z=parsed_args.z)
    
    try:
        rclpy.spin(drone_position_control_node)
    except KeyboardInterrupt:
        drone_position_control_node.publish_zero_velocity()
    finally:
        drone_position_control_node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()