import rclpy
import sys
import argparse
import math
import time
from rclpy import utilities
from geometry_msgs.msg import Twist
from sjtu_drone_control.drone_utils.drone_object import DroneObject
from sjtu_drone_control.drone_utils.controllers import PID


def quaternion_to_yaw(q):
    """
    Konwersja quaternion na kąt yaw (obrót wokół osi Z)
    :param q: geometry_msgs.msg.Quaternion
    :return: yaw w radianach
    """
    # Formuła Eulera dla yaw z quaternion
    siny_cosp = 2 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1 - 2 * (q.y * q.y + q.z * q.z)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return yaw


class SpiralTrajectory(DroneObject):
    def __init__(self, z=3.0, num_loops=3, max_radius=5.0, points_per_loop=20):
        """
        Lot po spirali w płaszczyźnie XY na stałej wysokości Z
        
        :param z: Wysokość lotu (metry)
        :param num_loops: Liczba pętli spirali
        :param max_radius: Maksymalny promień spirali (metry)
        :param points_per_loop: Liczba punktów na każdą pętlę (więcej = gładsza trajektoria)
        """
        super().__init__('spiral_trajectory')
        
        self.z = z
        self.num_loops = num_loops
        self.max_radius = max_radius
        self.points_per_loop = points_per_loop
        
        # Kontrolery PID dla każdej osi
        self.pid_x = PID(kp=1.0, ki=0.0, kd=0.5, min_out=-1.0, max_out=1.0)
        self.pid_y = PID(kp=1.0, ki=0.0, kd=0.5, min_out=-1.0, max_out=1.0)
        self.pid_z = PID(kp=1.0, ki=0.0, kd=0.5, min_out=-1.0, max_out=1.0)
        self.pid_yaw = PID(kp=2.0, ki=0.0, kd=0.3, min_out=-1.0, max_out=1.0)
        
        # Timer do kontrolowania ruchu
        self.control_timer = self.create_timer(0.1, self.control_loop)
        self.trajectory_index = 0
        self.trajectory_points = []
        self.target_reached = False
        
        self.get_logger().info(f'Spiral Trajectory initialized: z={z}m, loops={num_loops}, max_radius={max_radius}m')
        
        # Zakładamy że dron już wystartował
        # Włącz tryb kontroli prędkości (nie pozycji!)
        self.posCtrl(False)
        self.get_logger().info('Velocity control mode enabled')
        
        # Generuj punkty trajektorii
        self.generate_spiral_points()
        
        self.get_logger().info(f'Generated {len(self.trajectory_points)} trajectory points')
    
    def generate_spiral_points(self):
        """Generuj wszystkie punkty spirali z wyprzedzeniem"""
        total_points = self.num_loops * self.points_per_loop
        
        for i in range(total_points + 1):
            # Kąt zwiększa się - wielokrotne okrążenia
            angle = (i / self.points_per_loop) * 2 * math.pi
            
            # Promień rośnie liniowo od 0 do max_radius - SPIRALA ROZSZERZAJĄCA SIĘ
            radius = (i / total_points) * self.max_radius
            
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            
            # Oblicz kąt orientacji (styczna do spirali)
            # Kierunek lotu to pochodna trajektorii
            if i < total_points:
                next_angle = ((i + 1) / self.points_per_loop) * 2 * math.pi
                next_radius = ((i + 1) / total_points) * self.max_radius
                next_x = next_radius * math.cos(next_angle)
                next_y = next_radius * math.sin(next_angle)
                
                # Kąt yaw to atan2 różnicy pozycji
                yaw = math.atan2(next_y - y, next_x - x)
            else:
                # Ostatni punkt - użyj poprzedniego kąta
                if len(self.trajectory_points) > 0:
                    yaw = self.trajectory_points[-1][3]
                else:
                    yaw = 0.0
            
            self.trajectory_points.append((x, y, self.z, yaw))
    
    def control_loop(self):
        """Pętla kontrolna wykonywana co 100ms"""
        if self.trajectory_index >= len(self.trajectory_points):
            if not self.target_reached:
                self.get_logger().info('Spiral trajectory completed!')
                self.target_reached = True
                # Zatrzymaj drona
                self.publish_zero_velocity()
            return
        
        # Pobierz aktualną pozycję z sensora
        current_x = self.gt_pose.position.x
        current_y = self.gt_pose.position.y
        current_z = self.gt_pose.position.z
        
        # Pobierz orientację (konwersja quaternion -> yaw)
        current_yaw = quaternion_to_yaw(self.gt_pose.orientation)
        
        # Pobierz cel
        target_x, target_y, target_z, target_yaw = self.trajectory_points[self.trajectory_index]
        
        # Oblicz błędy pozycji
        error_x = target_x - current_x
        error_y = target_y - current_y
        error_z = target_z - current_z
        
        # Oblicz błąd orientacji (znormalizowany do [-pi, pi])
        error_yaw = target_yaw - current_yaw
        while error_yaw > math.pi:
            error_yaw -= 2 * math.pi
        while error_yaw < -math.pi:
            error_yaw += 2 * math.pi
        
        # Sprawdź czy dotarliśmy do punktu (tolerancja 0.3m)
        distance = math.sqrt(error_x**2 + error_y**2 + error_z**2)
        
        if distance < 0.3:
            self.trajectory_index += 1
            self.get_logger().info(
                f'Reached point {self.trajectory_index}/{len(self.trajectory_points)}: '
                f'x={target_x:.2f}, y={target_y:.2f}, z={target_z:.2f}, yaw={math.degrees(target_yaw):.1f}°',
                throttle_duration_sec=1.0
            )
            return
        
        # Oblicz prędkości sterujące przez PID
        dt = 0.1  # 100ms
        vel_x = self.pid_x.compute(error_x, dt)
        vel_y = self.pid_y.compute(error_y, dt)
        vel_z = self.pid_z.compute(error_z, dt)
        vel_yaw = self.pid_yaw.compute(error_yaw, dt)
        
        # Publikuj prędkości
        cmd = Twist()
        cmd.linear.x = vel_x
        cmd.linear.y = vel_y
        cmd.linear.z = vel_z
        cmd.angular.x = 0.0
        cmd.angular.y = 0.0
        cmd.angular.z = vel_yaw  # Obrót w kierunku lotu
        
        self.pubCmd.publish(cmd)
    
    def publish_zero_velocity(self):
        """Zatrzymaj drona"""
        cmd = Twist()
        self.pubCmd.publish(cmd)


def main(args=None):
    rclpy.init(args=args)
    
    # Parsuj argumenty
    args = utilities.remove_ros_args(sys.argv[1:])
    parser = argparse.ArgumentParser(description='Spiral Trajectory Flight')
    parser.add_argument('--z', type=float, default=3.0, 
                        help='Flight height in meters (default: 3.0)')
    parser.add_argument('--loops', type=int, default=3, 
                        help='Number of spiral loops (default: 3)')
    parser.add_argument('--radius', type=float, default=5.0, 
                        help='Maximum spiral radius in meters (default: 5.0)')
    parser.add_argument('--points', type=int, default=20, 
                        help='Points per loop for smoothness (default: 20)')
    
    parsed_args = parser.parse_args(args)
    
    # Walidacja parametrów
    if parsed_args.z <= 0:
        print("Error: Height (z) must be positive")
        return
    if parsed_args.loops <= 0:
        print("Error: Number of loops must be positive")
        return
    if parsed_args.radius <= 0:
        print("Error: Radius must be positive")
        return
    
    spiral_node = SpiralTrajectory(
        z=parsed_args.z,
        num_loops=parsed_args.loops,
        max_radius=parsed_args.radius,
        points_per_loop=parsed_args.points
    )
    
    try:
        rclpy.spin(spiral_node)
    except KeyboardInterrupt:
        spiral_node.get_logger().info('Trajectory interrupted by user')
        spiral_node.publish_zero_velocity()
    finally:
        spiral_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()