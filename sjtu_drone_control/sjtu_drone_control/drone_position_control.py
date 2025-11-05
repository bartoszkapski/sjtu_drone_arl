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
        """
        Kontroler pozycji drona z opcjonalnymi argumentami.
        ZAKŁADA ŻE DRON JUŻ LATA (takeoff wykonany wcześniej).
        
        :param x: Docelowa pozycja X (None = zachowaj obecną)
        :param y: Docelowa pozycja Y (None = zachowaj obecną)
        :param z: Docelowa pozycja Z (None = zachowaj obecną)
        """
        super().__init__('drone_position_control')

        self.get_logger().info('Initializing drone position control...')
        
        # Kontrolery PID dla każdej osi
        self.pid_x = PID(kp=1.5, ki=0.1, kd=0.5, min_out=-2.0, max_out=2.0)
        self.pid_y = PID(kp=1.5, ki=0.1, kd=0.5, min_out=-2.0, max_out=2.0)
        self.pid_z = PID(kp=2.0, ki=0.1, kd=0.8, min_out=-1.5, max_out=1.5)
        
        # Poczekaj na inicjalizację sensora pozycji
        time.sleep(1)
        
        # Pobierz OBECNĄ pozycję drona (który już lata)
        current_x = self.gt_pose.position.x
        current_y = self.gt_pose.position.y
        current_z = self.gt_pose.position.z
        
        self.get_logger().info(
            f'Current position: x={current_x:.2f}, y={current_y:.2f}, z={current_z:.2f}'
        )
        
        # Użyj podanych argumentów lub zachowaj obecne wartości
        self.target_x = x if x is not None else current_x
        self.target_y = y if y is not None else current_y
        self.target_z = z if z is not None else current_z
        
        self.get_logger().info(
            f'Target position:  x={self.target_x:.2f}, y={self.target_y:.2f}, z={self.target_z:.2f}'
        )
        
        # Włącz tryb kontroli prędkości (NIE pozycji!)
        self.posCtrl(False)
        
        # Timer do aktywnego kontrolowania pozycji
        self.control_timer = self.create_timer(0.05, self.control_loop)  # 50ms
        self.target_reached = False

    def control_loop(self):
        """Pętla kontrolna wykonywana co 50ms - aktywnie utrzymuje pozycję"""
        if self.target_reached:
            return
        
        # Pobierz aktualną pozycję
        current_x = self.gt_pose.position.x
        current_y = self.gt_pose.position.y
        current_z = self.gt_pose.position.z
        
        # Oblicz błędy
        error_x = self.target_x - current_x
        error_y = self.target_y - current_y
        error_z = self.target_z - current_z
        
        # Sprawdź czy dotarliśmy (tolerancja 0.2m)
        distance = math.sqrt(error_x**2 + error_y**2 + error_z**2)
        
        if distance < 0.2:
            if not self.target_reached:
                self.get_logger().info(
                    f'✓ Target reached! Final position: x={current_x:.2f}, y={current_y:.2f}, z={current_z:.2f}'
                )
                self.target_reached = True
                # Zatrzymaj drona (zerowe prędkości)
                self.publish_zero_velocity()
            return
        
        # Oblicz prędkości sterujące przez PID
        dt = 0.05  # 50ms
        vel_x = self.pid_x.compute(error_x, dt)
        vel_y = self.pid_y.compute(error_y, dt)
        vel_z = self.pid_z.compute(error_z, dt)
        
        # Publikuj prędkości
        cmd = Twist()
        cmd.linear.x = vel_x
        cmd.linear.y = vel_y
        cmd.linear.z = vel_z
        cmd.angular.x = 0.0
        cmd.angular.y = 0.0
        cmd.angular.z = 0.0
        
        self.pubCmd.publish(cmd)
        
        # Log co 1s (20 iteracji * 50ms)
        if not hasattr(self, '_log_counter'):
            self._log_counter = 0
        self._log_counter += 1
        if self._log_counter >= 20:
            self._log_counter = 0
            self.get_logger().info(
                f'Flying... distance to target: {distance:.2f}m | '
                f'current: ({current_x:.1f}, {current_y:.1f}, {current_z:.1f})'
            )
    
    def publish_zero_velocity(self):
        """Zatrzymaj drona"""
        cmd = Twist()
        self.pubCmd.publish(cmd)


def main(args=None):
    rclpy.init(args=args)
    
    # Parsuj argumenty
    args = utilities.remove_ros_args(sys.argv[1:])
    parser = argparse.ArgumentParser(
        description='Drone Position Control - assumes drone is already flying (takeoff done externally)'
    )
    parser.add_argument('--x', type=float, default=None, 
                        help='Target X position in meters (default: keep current)')
    parser.add_argument('--y', type=float, default=None, 
                        help='Target Y position in meters (default: keep current)')
    parser.add_argument('--z', type=float, default=None, 
                        help='Target Z position/height in meters (default: keep current)')
    
    parsed_args = parser.parse_args(args)
    
    # Utwórz node z podanymi parametrami
    drone_position_control_node = DronePositionControl(
        x=parsed_args.x,
        y=parsed_args.y,
        z=parsed_args.z
    )
    
    try:
        rclpy.spin(drone_position_control_node)
    except KeyboardInterrupt:
        drone_position_control_node.get_logger().info('Shutting down...')
        drone_position_control_node.publish_zero_velocity()
    finally:
        drone_position_control_node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()