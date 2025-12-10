#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from enum import Enum
import time
import math
import json
from geometry_msgs.msg import Pose, Vector3
from std_msgs.msg import Bool, String
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'drone_utils'))
from drone_object import DroneObject
from controllers import PID
from geometry_msgs.msg import Twist


class MissionConfig:
    # param kwadrat
    SQUARE_START_SIZE = 4.0                 # poczatkowy rozmiar kwadratu
    SQUARE_INCREMENT = 2.0                  # o ile zwiększać
    SQUARE_MAX_SIZE = 20.0                  # max rozmiar kwadratru
    
    # param lot
    SEARCH_ALTITUDE = 10.0                  # wysokośc lotu 
    DESCENT_ALTITUDE = 1.0                  # wyokośc przed lądowaniem
    CIRCLE_RADIUS = 2.0                     # promień krążenia nad obiektem
    CIRCLE_ROTATIONS = 2.0                  # liczba pełnych obrotów nad obiektem

    
    # PID 
    PID_KP = 0.5     
    PID_KI = 0.02     
    PID_KD = 0.5     
    PID_MAX_VEL = 1.0 
    
    # centrowanie
    CENTERING_TOLERANCE = 0.5               # tolerancja odległości
    
    # kamera
    CAMERA_HORIZONTAL = 60.0                # poziomy zakres widzenia
    CAMERA_VERTICAL = 33.75                 # pionowy zakres widzenia
    
    # detekcja YOLO
    DETECTION_CONFIDENCE_THRESHOLD = 0.8    # minimalny próg detekcji
    DETECTION_CONSECUTIVE_FRAMES = 7        # liczba kolejnych klatek potrzebnych
    
    # czasówki
    TAKEOFF_WAIT_TIME = 3.0                 # czas oczekiwania po starcie
    WAYPOINT_TOLERANCE = 1.5                # tolerancja odległości do uznania punktu za osiągnięty
    
    # częstotliwość sterowań
    CONTROL_LOOP_RATE = 5.0      


class MissionState(Enum):
    IDLE = 0
    TAKEOFF = 1
    EXPANDING_SQUARE_SEARCH = 2
    BACK_TO_HUMAN = 3 
    CENTERING = 4  
    CIRCLING = 5
    RETURN_HOME = 6
    DESCENDING = 7  
    LANDING = 8
    COMPLETE = 9

class DroneSearchMission(DroneObject):   
    def __init__(self):
        super().__init__('drone_search_mission')
        
        self.config = MissionConfig()

        self.current_state = MissionState.IDLE
        self.last_logged_state = None
        self.state_start_time = time.time()
        self.home_position = None
        self.a = 0
        self.b = 0 
    
        self.current_square_size = self.config.SQUARE_START_SIZE
        self.square_waypoints = []
        self.current_waypoint_idx = 0

        self.detection_buffer = []
        self.human_detected_confirmed = False
        self.detection_drone_position = None 
        self.detection_position = None 
        self.detection_bbox_center = None  
        
        self.circle_angle = 0.0
        self.circle_center = None

        
        self.pid_x = PID(
            kp=self.config.PID_KP,
            ki=self.config.PID_KI,
            kd=self.config.PID_KD,
            min_out=-self.config.PID_MAX_VEL,
            max_out=self.config.PID_MAX_VEL
        )
        self.pid_y = PID(
            kp=self.config.PID_KP,
            ki=self.config.PID_KI,
            kd=self.config.PID_KD,
            min_out=-self.config.PID_MAX_VEL,
            max_out=self.config.PID_MAX_VEL
        )
        self.pid_z = PID(
            kp=self.config.PID_KP * 1.5,  
            ki=self.config.PID_KI,
            kd=self.config.PID_KD * 1.2,
            min_out=-self.config.PID_MAX_VEL * 0.8,
            max_out=self.config.PID_MAX_VEL * 0.8
        )
        
        self.target_position = None
        self.velocity_mode_active = False
    
        # yolo sub
        self.sub_detection = self.create_subscription(String,'/detection/human_detected',self.cb_detection, 10)
        
        # status pub
        self.pub_mission_status = self.create_publisher(String,'/mission/status',10)
        
        self.control_timer = self.create_timer(1.0/self.config.CONTROL_LOOP_RATE,self.control_loop)
        
    

    def control_loop(self):
        # status misji pub
        status_msg = String()
        status_msg.data = json.dumps({
            'state': self.current_state.name,
            'square_size': self.current_square_size,
            'waypoint': f'{self.current_waypoint_idx}/{len(self.square_waypoints)}',
            'detections_buffer': len(self.detection_buffer),
            'human_confirmed': self.human_detected_confirmed
        })
        self.pub_mission_status.publish(status_msg)
        
        if self.current_state != self.last_logged_state:
            self.logger.info(f'***STAN: {self.current_state.name}***')
            self.last_logged_state = self.current_state
    
        
        # maszyna stanów
        if self.current_state == MissionState.IDLE:
            self.state_idle()
        elif self.current_state == MissionState.TAKEOFF:
            self.state_takeoff()
        elif self.current_state == MissionState.EXPANDING_SQUARE_SEARCH:
            self.state_expanding_square_search()
        elif self.current_state == MissionState.BACK_TO_HUMAN:
            self.state_back_to_human()
        elif self.current_state == MissionState.CENTERING:
            self.state_centering()
        elif self.current_state == MissionState.CIRCLING:
            self.state_circling()
        elif self.current_state == MissionState.RETURN_HOME:
            self.state_return_home()
        elif self.current_state == MissionState.DESCENDING:
            self.state_descending()
        elif self.current_state == MissionState.LANDING:
            self.state_landing()
        elif self.current_state == MissionState.COMPLETE:
            self.state_complete()
    

    def state_idle(self):
        if time.time() - self.state_start_time > 1.0:
            self.transition_to(MissionState.TAKEOFF)
    
    def state_takeoff(self):
        current_height = self.gt_pose.position.z
        elapsed = time.time() - self.state_start_time

        if elapsed < 0.5:
            self.home_position = self.gt_pose.position
            self.posCtrl(True)
            time.sleep(0.2)
            if current_height < 0.5:
                self.takeOff()
                time.sleep(0.5)
        
        # fly up
        if current_height < self.config.SEARCH_ALTITUDE:
            self.moveTo(self.home_position.x, self.home_position.y, self.config.SEARCH_ALTITUDE)
        else:
            if elapsed >= self.config.TAKEOFF_WAIT_TIME:
                self.generate_square_waypoints()
                self.transition_to(MissionState.EXPANDING_SQUARE_SEARCH)
    
    def state_expanding_square_search(self):
        if not self.velocity_mode_active:
            self.posCtrl(False) 
            self.velocity_mode_active = True
    
        if self.human_detected_confirmed:
            self.detection_drone_position = (self.gt_pose.position.x,self.gt_pose.position.y, self.gt_pose.position.z)
            if self.a == 0:
                self.logger.info(f'Człowiek znaleziony')
                self.a = 1
            self.transition_to(MissionState.BACK_TO_HUMAN)
            return
        
        
        if self.current_waypoint_idx < len(self.square_waypoints):
            wp = self.square_waypoints[self.current_waypoint_idx]
            dist = self.move_to_position_pid(wp[0], wp[1], wp[2])
            
            if dist < self.config.WAYPOINT_TOLERANCE:
                self.current_waypoint_idx += 1
        else:
            self.current_square_size += self.config.SQUARE_INCREMENT
            if self.current_square_size > self.config.SQUARE_MAX_SIZE:
                self.logger.warn(f'Nie znaleziono człowieka')
                self.transition_to(MissionState.RETURN_HOME)
                return
            
            self.generate_square_waypoints()
            self.current_waypoint_idx = 0
    
    def calculate_human_world_position(self):
        drone_x = self.gt_pose.position.x
        drone_y = self.gt_pose.position.y
        drone_z = self.gt_pose.position.z
        
        bbox_x_norm = self.detection_bbox_center['x']
        bbox_y_norm = self.detection_bbox_center['y']
    
        offset_x_norm = bbox_x_norm - 0.5 
        offset_y_norm = bbox_y_norm - 0.5
        
        camera_h_rad = math.radians(self.config.CAMERA_HORIZONTAL)
        camera_v_rad = math.radians(self.config.CAMERA_VERTICAL)
        
        ground_width = 2 * drone_z * math.tan(camera_h_rad / 2)
        ground_height = 2 * drone_z * math.tan(camera_v_rad / 2)
        
        offset_x_meters = offset_x_norm * ground_width
        offset_y_meters = offset_y_norm * ground_height
        
        human_x = drone_x + offset_y_meters  
        human_y = drone_y - offset_x_meters  
        human_z = 0.0
        
        return (human_x, human_y, human_z)
    
    def state_back_to_human(self):
        target_x = self.detection_drone_position[0]
        target_y = self.detection_drone_position[1]
        target_z = self.config.SEARCH_ALTITUDE
        
        dist = self.move_to_position_pid(target_x, target_y, target_z)
        
        horizontal_dist = math.sqrt((self.gt_pose.position.x - target_x)**2 +(self.gt_pose.position.y - target_y)**2)
        
        if horizontal_dist < 0.3:  
            elapsed = time.time() - self.state_start_time
            if elapsed > 1.0: 
                human_world_pos = self.calculate_human_world_position()
                

                if human_world_pos:
                    self.detection_position = human_world_pos
                    self.transition_to(MissionState.CENTERING)
                else:
                    self.detection_position = (self.gt_pose.position.x, self.gt_pose.position.y, 0.0)
                    self.transition_to(MissionState.CENTERING)

    
    def state_centering(self):
        target_x = self.detection_position[0]
        target_y = self.detection_position[1]
        target_z = self.config.SEARCH_ALTITUDE  

        dist = self.move_to_position_pid(target_x, target_y, target_z)
        
        horizontal_dist = math.sqrt((self.gt_pose.position.x - target_x)**2 +(self.gt_pose.position.y - target_y)**2)
        
        if horizontal_dist < self.config.CENTERING_TOLERANCE:
            self.circle_center = (self.gt_pose.position.x, self.gt_pose.position.y)
            self.circle_angle = 0.0
            self.transition_to(MissionState.CIRCLING)

    
    def state_circling(self):
        angle_increment = 0.05 
        self.circle_angle += angle_increment
        total_rotations = self.circle_angle / (2 * math.pi)
        
        if total_rotations >= self.config.CIRCLE_ROTATIONS:
            self.transition_to(MissionState.RETURN_HOME)
            return

        x = self.circle_center[0] + self.config.CIRCLE_RADIUS * math.cos(self.circle_angle)
        y = self.circle_center[1] + self.config.CIRCLE_RADIUS * math.sin(self.circle_angle)
        z = self.config.SEARCH_ALTITUDE
        
        self.move_to_position_pid(x, y, z)
        
    
    def state_return_home(self):
        dist = self.move_to_position_pid(self.home_position.x,self.home_position.y,self.config.SEARCH_ALTITUDE)
        if dist < 1.0: 
            self.transition_to(MissionState.DESCENDING)
    
    def state_descending(self):
        self.move_to_position_pid(self.home_position.x, self.home_position.y, self.config.DESCENT_ALTITUDE)
        
        current_alt = self.gt_pose.position.z
        if current_alt < self.config.DESCENT_ALTITUDE + 0.2:  
            self.transition_to(MissionState.LANDING)

    def state_landing(self):
        if self.b == 0:
            self.logger.info('Lądowanie...')
            self.b =1 
        self.land()
         
        if time.time() - self.state_start_time > 5.0:
            self.transition_to(MissionState.COMPLETE)
    
    def state_complete(self):
        self.logger.info('Koniec misji.')
        self.control_timer.cancel()
    
    def transition_to(self, new_state: MissionState):
        self.current_state = new_state
        self.state_start_time = time.time()
        
    
    def generate_square_waypoints(self):
        half_size = self.current_square_size / 2
        
        center_x = self.home_position.x
        center_y = self.home_position.y
        
        z = self.config.SEARCH_ALTITUDE
        self.square_waypoints = [
            (center_x + half_size, center_y + half_size, z), 
            (center_x + half_size + 0.5, center_y - half_size - 0.5, z), 
            (center_x - half_size -1, center_y - half_size - 1, z),  
            (center_x - half_size - 1.5, center_y + half_size + 1.5, z), 

        ]
        
        self.current_waypoint_idx = 0

    
    def move_to_position_pid(self, target_x, target_y, target_z):
        current_x = self.gt_pose.position.x
        current_y = self.gt_pose.position.y
        current_z = self.gt_pose.position.z
        
        error_x = target_x - current_x
        error_y = target_y - current_y
        error_z = target_z - current_z
        
        distance = math.sqrt(error_x**2 + error_y**2 + error_z**2)
        
        dt = 1.0 / self.config.CONTROL_LOOP_RATE 
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
        
        return distance
    
    def cb_detection(self, msg: String):
        try:
            data = json.loads(msg.data)
            detected = data.get('detected', False)
            confidence = data.get('confidence', 0.0)
            count = data.get('count', 0)
            bbox_center = data.get('bbox_center', None) 

            if detected and confidence >= self.config.DETECTION_CONFIDENCE_THRESHOLD:
                self.detection_buffer.append(confidence)
             
                if bbox_center:
                    self.detection_bbox_center = bbox_center
                
                max_buffer = self.config.DETECTION_CONSECUTIVE_FRAMES + 5
                if len(self.detection_buffer) > max_buffer:
                    self.detection_buffer = self.detection_buffer[-max_buffer:]
                
                if len(self.detection_buffer) >= self.config.DETECTION_CONSECUTIVE_FRAMES:
                    last_n = self.detection_buffer[-self.config.DETECTION_CONSECUTIVE_FRAMES:]
                    if all(c >= self.config.DETECTION_CONFIDENCE_THRESHOLD for c in last_n):
                        if not self.human_detected_confirmed:
                            avg_conf = sum(last_n) / len(last_n)
                            self.logger.info(f'YOLO: Pewność wykrycia człowieka: {avg_conf:.2f}')
                            self.human_detected_confirmed = True
            else:
                if self.detection_buffer:
                    self.detection_buffer.clear()
                    
        except Exception as e:
            self.logger.error(f'Error{e}')

def main(args=None):
    rclpy.init(args=args)
    mission = DroneSearchMission()
    
    try:
        rclpy.spin(mission)
    finally:
        mission.land()
        mission.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
