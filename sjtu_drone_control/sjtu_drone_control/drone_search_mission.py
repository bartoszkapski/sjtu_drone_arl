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


# ============================================================================
#                           SEARCHING PARAMETERS
# ============================================================================
class MissionConfig:

    # Parametry kwadratu poszukiwań
    SQUARE_START_SIZE = 2.0      # [m] poczatkowy rozmiar kwadratu
    SQUARE_INCREMENT = 2.0        # [m] o ile zwiększać
    SQUARE_MAX_SIZE = 20.0        # [m] max rozmiar kwadratru
    
    # Parametry lotu poszukiwawczego
    SEARCH_ALTITUDE = 10.0         # [m] wysokośc lotu 
    DESCENT_ALTITUDE = 1.0         # [m] zschodzenie na zadaną wyokośc przed lądowaniem
    CIRCLE_RADIUS = 2.0          # [m] promień krążenia nad obiektem
    CIRCLE_ROTATIONS = 2.0        # liczba pełnych obrotów nad obiektem
    SEARCH_SPEED_DELAY = 0.5      # [s] dodatkowe opóźnienie między punktami trasy
    
    # PID 
    PID_KP = 0.8      
    PID_KI = 0.10     
    PID_KD = 0.3     
    PID_MAX_VEL = 1.0 
    
    # Centrowanie
    CENTERING_TOLERANCE = 0.1 # [m] tolerancja odległości do uznania za wycentrowany
    
    # Parametry kamery 
    CAMERA_FOV_HORIZONTAL = 60.0  # [degrees] poziomy kąt widzenia (z URDF: 1.047 rad)
    CAMERA_FOV_VERTICAL = 33.75   # [degrees] pionowy kąt widzenia (obliczony: 60°/1.778 aspect ratio)
    
    # Parametry detekcji YOLO
    DETECTION_CONFIDENCE_THRESHOLD = 0.8   # minimalny próg detekcji
    DETECTION_CONSECUTIVE_FRAMES = 5       # liczba kolejnych klatek potrzebnych
    
    # Czasówki
    TAKEOFF_WAIT_TIME = 3.0       # [s] czas oczekiwania po starcie
    WAYPOINT_TOLERANCE = 0.3      # [m] tolerancja odległości do uznania punktu za osiągnięty
    
    # Częstotliwość pętli sterowania
    CONTROL_LOOP_RATE = 5.0       # [Hz] 


# ============================================================================
#                               MISSION STATES
# ============================================================================
class MissionState(Enum):
    IDLE = 0
    TAKEOFF = 1
    EXPANDING_SQUARE_SEARCH = 2
    HOVERING = 3 
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
        
        # Mission state
        self.current_state = MissionState.IDLE
        self.state_start_time = time.time()
        
        # Home position (for return)
        self.home_position = None
        
        # Expanding square search
        self.current_square_size = self.config.SQUARE_START_SIZE
        self.square_waypoints = []
        self.current_waypoint_idx = 0
        self.last_waypoint_reached_time = 0.0  # For slower flight
        
        # Detection tracking
        self.detection_buffer = []  # Last N detection results
        self.human_detected_confirmed = False
        self.detection_drone_position = None  # Drone position at detection moment
        self.detection_position = None  # Calculated human position on ground (after hovering)
        self.detection_bbox_center = None  # Bbox center in frame (0-1)
        
        # Circling
        self.circle_angle = 0.0
        self.circle_center = None
        self.last_logged_circle_segment = -1  # Track last logged segment to avoid duplicates
        
        # PID Controllers for closed-loop position control (slower flight)
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
            kp=self.config.PID_KP * 1.5,  # Z-axis slightly more responsive
            ki=self.config.PID_KI,
            kd=self.config.PID_KD * 1.2,
            min_out=-self.config.PID_MAX_VEL * 0.8,
            max_out=self.config.PID_MAX_VEL * 0.8
        )
        
        # Current target position for PID
        self.target_position = None
        
        # Control mode flag
        self.velocity_mode_active = False
        
        # Subscribe to YOLO detection results
        self.sub_detection = self.create_subscription(
            String,
            '/detection/human_detected',
            self.cb_detection,
            10
        )
        
        # Publisher for mission status
        self.pub_mission_status = self.create_publisher(
            String,
            '/mission/status',
            10
        )
        
        # Main control timer
        self.control_timer = self.create_timer(
            1.0 / self.config.CONTROL_LOOP_RATE,
            self.control_loop
        )
        
        self.logger.info('╔══════════════════════════════════════════════════════════╗')
        self.logger.info('║   🚁 DRONE HUMAN SEARCH MISSION - STARTED 🚁           ║')
        self.logger.info('╚══════════════════════════════════════════════════════════╝')
        self.logger.info(f'📐 Search pattern: {self.config.SQUARE_START_SIZE}m → '
                        f'{self.config.SQUARE_MAX_SIZE}m (increment: {self.config.SQUARE_INCREMENT}m)')
        self.logger.info(f'🎯 Detection threshold: {self.config.DETECTION_CONFIDENCE_THRESHOLD} '
                        f'({self.config.DETECTION_CONSECUTIVE_FRAMES} consecutive frames)')
        self.logger.info(f'✈️  Flight altitude: {self.config.SEARCH_ALTITUDE}m')
        self.logger.info('─' * 58)
    
    # ========================================================================
    # MAIN CONTROL LOOP
    # ========================================================================
    
    def control_loop(self):
        """Main state machine control loop"""
        
        # Publish mission status
        status_msg = String()
        status_msg.data = json.dumps({
            'state': self.current_state.name,
            'square_size': self.current_square_size,
            'waypoint': f'{self.current_waypoint_idx}/{len(self.square_waypoints)}',
            'detections_buffer': len(self.detection_buffer),
            'human_confirmed': self.human_detected_confirmed
        })
        self.pub_mission_status.publish(status_msg)
        
        # State machine
        if self.current_state == MissionState.IDLE:
            self.state_idle()
        elif self.current_state == MissionState.TAKEOFF:
            self.state_takeoff()
        elif self.current_state == MissionState.EXPANDING_SQUARE_SEARCH:
            self.state_expanding_square_search()
        elif self.current_state == MissionState.HOVERING:
            self.state_hovering()
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
    
    # ========================================================================
    # STATE HANDLERS
    # ========================================================================
    
    def state_idle(self):
        """IDLE - Initial state, transition to takeoff"""
        if time.time() - self.state_start_time > 1.0:
            self.transition_to(MissionState.TAKEOFF)
    
    def state_takeoff(self):
        """TAKEOFF - Launch drone and wait"""
        current_height = self.gt_pose.position.z
        elapsed = time.time() - self.state_start_time
        
        # Save home position at start
        if elapsed < 0.5:
            self.home_position = self.gt_pose.position
            self.logger.info(f'🏠 Home position saved: x={self.home_position.x:.1f}, '
                           f'y={self.home_position.y:.1f}, z={self.home_position.z:.1f}')
            self.posCtrl(True)
            time.sleep(0.2)
            if current_height < 0.5:
                self.takeOff()
                time.sleep(0.5)
        
        # Climb to search altitude
        if current_height < self.config.SEARCH_ALTITUDE * 0.9:
            self.moveTo(
                self.home_position.x,
                self.home_position.y,
                self.config.SEARCH_ALTITUDE
            )
            # Log every 2 seconds instead of every 0.5s
            if int(elapsed) % 2 == 0 and int(elapsed * 10) % 10 == 0:
                self.logger.info(f'⬆️  Climbing... {current_height:.1f}m / {self.config.SEARCH_ALTITUDE:.1f}m')
        else:
            # Reached altitude - wait configured time
            if elapsed >= self.config.TAKEOFF_WAIT_TIME + 5.0:
                self.logger.info(f'✅ Takeoff complete - waiting {self.config.TAKEOFF_WAIT_TIME}s')
                self.logger.info('🔍 Starting search mission...')
                self.generate_square_waypoints()
                self.transition_to(MissionState.EXPANDING_SQUARE_SEARCH)
    
    def state_expanding_square_search(self):
        """EXPANDING_SQUARE_SEARCH - Search with increasing square sizes (using PID for slower flight)"""
        
        # Switch to velocity mode on first entry (for PID control)
        if not self.velocity_mode_active:
            self.logger.info('🔧 Switching to velocity mode for PID control...')
            self.posCtrl(False)  # Velocity mode
            self.velocity_mode_active = True
            self.logger.info('🎮 Velocity mode ACTIVE - PID control ready')
        
        # Check if human detected (confirmed by N consecutive frames)
        if self.human_detected_confirmed:
            self.logger.info('╔══════════════════════════════════════════════╗')
            self.logger.info('║  🎯 HUMAN DETECTED! Returning to position...║')
            self.logger.info('╚══════════════════════════════════════════════╝')
            
            # Save drone position at detection moment
            self.detection_drone_position = (
                self.gt_pose.position.x,
                self.gt_pose.position.y,
                self.gt_pose.position.z
            )
            self.logger.info(f'📍 Detection at: x={self.detection_drone_position[0]:.2f}m, '
                           f'y={self.detection_drone_position[1]:.2f}m')
            
            # First: return to detection position and stabilize
            self.transition_to(MissionState.HOVERING)
            return
        
        # Fly current square waypoints
        if self.current_waypoint_idx < len(self.square_waypoints):
            # Check if we need to wait (slower flight for better detection)
            time_since_last_wp = time.time() - self.last_waypoint_reached_time
            if time_since_last_wp < self.config.SEARCH_SPEED_DELAY:
                # Still waiting - hover at current position
                return
            
            wp = self.square_waypoints[self.current_waypoint_idx]
            
            # Use PID control for slower, more precise flight
            dist = self.move_to_position_pid(wp[0], wp[1], wp[2])
            
            # Check if reached waypoint
            if dist < self.config.WAYPOINT_TOLERANCE:
                self.current_waypoint_idx += 1
                self.last_waypoint_reached_time = time.time()  # Mark time for delay
                self.logger.info(f'📍 Waypoint {self.current_waypoint_idx}/{len(self.square_waypoints)} '
                               f'reached (square: {self.current_square_size:.0f}m)')
        else:
            # Completed current square - expand
            self.current_square_size += self.config.SQUARE_INCREMENT
            
            if self.current_square_size > self.config.SQUARE_MAX_SIZE:
                self.logger.warn(f'⚠️  Max search area reached ({self.config.SQUARE_MAX_SIZE}m) - '
                               'human not found')
                self.transition_to(MissionState.RETURN_HOME)
                return
            
            self.logger.info(f'🔍 Expanding search - new square size: {self.current_square_size:.0f}m')
            self.generate_square_waypoints()
            self.current_waypoint_idx = 0
    
    def calculate_human_world_position(self):
        """
        Calculate human's world position from camera detection
        
        Returns: (x, y, z=0) world coordinates or None if calculation failed
        """
        if not self.detection_bbox_center:
            self.logger.warn('⚠️  No bbox center available for position calculation')
            return None
        
        # Current drone position
        drone_x = self.gt_pose.position.x
        drone_y = self.gt_pose.position.y
        drone_z = self.gt_pose.position.z
        
        # Bbox center in normalized frame (0-1)
        # 0.5, 0.5 = center of frame
        # x: 0=left, 1=right
        # y: 0=top, 1=bottom
        bbox_x_norm = self.detection_bbox_center['x']
        bbox_y_norm = self.detection_bbox_center['y']
        
        # Convert to offset from center (-0.5 to +0.5)
        offset_x_norm = bbox_x_norm - 0.5  # -0.5 = left edge, +0.5 = right edge
        offset_y_norm = bbox_y_norm - 0.5  # -0.5 = top edge, +0.5 = bottom edge
        
        # Calculate field of view at ground level
        # tan(FOV/2) = (width/2) / height
        fov_h_rad = math.radians(self.config.CAMERA_FOV_HORIZONTAL)
        fov_v_rad = math.radians(self.config.CAMERA_FOV_VERTICAL)
        
        ground_width = 2 * drone_z * math.tan(fov_h_rad / 2)
        ground_height = 2 * drone_z * math.tan(fov_v_rad / 2)
        
        # Calculate offset in meters
        offset_x_meters = offset_x_norm * ground_width
        offset_y_meters = offset_y_norm * ground_height
        
        # Human world position (camera points straight down in drone frame)
        # In ROS/Gazebo convention for downward camera:
        # - Camera X-axis points right → affects world Y
        # - Camera Y-axis points down → affects world X
        human_x = drone_x + offset_y_meters  # Forward/backward
        human_y = drone_y - offset_x_meters  # Left/right (inverted)
        human_z = 0.0  # On ground
        
        self.logger.info(f'📐 Bbox in frame: x={bbox_x_norm:.2f}, y={bbox_y_norm:.2f}')
        self.logger.info(f'📐 Camera offset: x={offset_x_norm:.2f}, y={offset_y_norm:.2f}')
        self.logger.info(f'📐 Ground offset: {offset_x_meters:.2f}m x {offset_y_meters:.2f}m')
        self.logger.info(f'📐 FOV at {drone_z:.1f}m altitude: {ground_width:.1f}m x {ground_height:.1f}m')
        
        return (human_x, human_y, human_z)
    
    def state_hovering(self):
        """HOVERING - Return to detection position and stabilize before centering"""
        
        if not self.detection_drone_position:
            self.logger.error('❌ No detection position saved!')
            self.transition_to(MissionState.RETURN_HOME)
            return
        
        # Target: exact position where detection occurred
        target_x = self.detection_drone_position[0]
        target_y = self.detection_drone_position[1]
        target_z = self.config.SEARCH_ALTITUDE
        
        # Use PID to return to detection position
        dist = self.move_to_position_pid(target_x, target_y, target_z)
        
        # Check if stabilized at detection position
        horizontal_dist = math.sqrt(
            (self.gt_pose.position.x - target_x)**2 +
            (self.gt_pose.position.y - target_y)**2
        )
        
        if horizontal_dist < 0.3:  # Stabilized within 30cm
            # Now read fresh bbox and calculate human position
            self.logger.info('✅ Hovering stabilized! Reading camera...')
            
            # Wait a moment for stable camera reading
            elapsed = time.time() - self.state_start_time
            if elapsed > 1.0:  # Wait 1 second for stable hover
                # Calculate human position NOW from stable position
                human_world_pos = self.calculate_human_world_position()
                
                if human_world_pos:
                    self.detection_position = human_world_pos
                    self.logger.info(f'📍 Human position calculated: x={human_world_pos[0]:.2f}m, y={human_world_pos[1]:.2f}m')
                    self.transition_to(MissionState.CENTERING)
                else:
                    self.logger.warn('⚠️  No bbox data - assuming human directly below')
                    self.detection_position = (self.gt_pose.position.x, self.gt_pose.position.y, 0.0)
                    self.transition_to(MissionState.CENTERING)
        else:
            # Log every 2 seconds while returning
            if int(time.time()) % 2 == 0 and int(time.time() * 10) % 10 == 0:
                self.logger.info(f'🔄 Returning to detection point... {horizontal_dist:.2f}m')
    
    def state_centering(self):
        """CENTERING - Center drone directly above calculated human position"""
        
        # Target: calculated human position on ground
        target_x = self.detection_position[0]
        target_y = self.detection_position[1]
        target_z = self.config.SEARCH_ALTITUDE  # Keep altitude
        
        # Use PID for precise centering
        dist = self.move_to_position_pid(target_x, target_y, target_z)
        
        # Check if centered (horizontal distance only)
        horizontal_dist = math.sqrt(
            (self.gt_pose.position.x - target_x)**2 +
            (self.gt_pose.position.y - target_y)**2
        )
        
        if horizontal_dist < self.config.CENTERING_TOLERANCE:
            self.logger.info(f'✅ Centered above human! (offset: {horizontal_dist:.2f}m)')
            self.circle_center = (self.gt_pose.position.x, self.gt_pose.position.y)
            self.circle_angle = 0.0
            self.transition_to(MissionState.CIRCLING)
        else:
            # Log every 2 seconds
            if int(time.time()) % 2 == 0 and int(time.time() * 10) % 10 == 0:
                self.logger.info(f'🎯 Centering over human... {horizontal_dist:.2f}m remaining')
    
    def state_circling(self):
        """CIRCLING - Circle over detected human"""
        
        # Calculate circle angle increment (for smooth motion)
        angle_increment = 0.05  # ~3 degrees per step at 5Hz = ~6 sec per rotation
        self.circle_angle += angle_increment
        
        total_rotations = self.circle_angle / (2 * math.pi)
        
        if total_rotations >= self.config.CIRCLE_ROTATIONS:
            self.logger.info(f'✅ Circling complete ({self.config.CIRCLE_ROTATIONS} rotations)')
            self.transition_to(MissionState.RETURN_HOME)
            return
        
        # Calculate position on circle
        x = self.circle_center[0] + self.config.CIRCLE_RADIUS * math.cos(self.circle_angle)
        y = self.circle_center[1] + self.config.CIRCLE_RADIUS * math.sin(self.circle_angle)
        z = self.config.SEARCH_ALTITUDE
        
        # Use PID for smooth circling
        self.move_to_position_pid(x, y, z)
        
        # Log progress every ~90 degrees (4 times per rotation) - but only once per segment
        current_segment = int(self.circle_angle * 2 / math.pi)  # 0, 1, 2, 3 for each 90° segment
        if current_segment != self.last_logged_circle_segment:
            self.last_logged_circle_segment = current_segment
            self.logger.info(f'⭕ Circling... rotation {total_rotations:.1f}/{self.config.CIRCLE_ROTATIONS}')
    
    def state_return_home(self):
        """RETURN_HOME - Return to launch position at search altitude"""
        
        if self.home_position is None:
            self.logger.error('❌ No home position saved!')
            self.transition_to(MissionState.DESCENDING)
            return
        
        # Fly to home at search altitude using PID
        dist = self.move_to_position_pid(
            self.home_position.x,
            self.home_position.y,
            self.config.SEARCH_ALTITUDE
        )
        
        if dist < 2.0:  # Increased tolerance for horizontal position
            self.logger.info('✅ Returned to home position - preparing to descend')
            self.transition_to(MissionState.DESCENDING)
        else:
            # Log every 3 seconds
            if int(time.time()) % 3 == 0 and int(time.time() * 10) % 10 == 0:
                self.logger.info(f'🏠 Returning home... {dist:.1f}m remaining')
    
    def state_descending(self):
        """DESCENDING - Descend to 1m altitude above home before landing"""
        
        if self.home_position is None:
            self.logger.error('❌ No home position saved!')
            self.transition_to(MissionState.LANDING)
            return
        
        # Fly to 1m altitude above home using PID
        self.move_to_position_pid(
            self.home_position.x,
            self.home_position.y,
            self.config.DESCENT_ALTITUDE
        )
        
        # Check if reached descent altitude
        current_alt = self.gt_pose.position.z
        
        if current_alt < self.config.DESCENT_ALTITUDE + 0.2:  # Within 0.2m of target (1.0m + 0.2m = 1.2m max)
            self.logger.info(f'✅ Reached descent altitude ({current_alt:.1f}m) - ready to land')
            self.transition_to(MissionState.LANDING)
        else:
            # Log every 2 seconds
            if int(time.time()) % 2 == 0 and int(time.time() * 10) % 10 == 0:
                self.logger.info(f'⬇️  Descending... {current_alt:.1f}m / {self.config.DESCENT_ALTITUDE}m')
    
    def state_landing(self):
        """LANDING - Land the drone"""
        self.logger.info('🛬 Landing...')
        self.land()
        
        if time.time() - self.state_start_time > 5.0:
            self.transition_to(MissionState.COMPLETE)
    
    def state_complete(self):
        """COMPLETE - Mission finished"""
        self.logger.info('╔══════════════════════════════════════════════════════════╗')
        self.logger.info('║        ✅ MISSION COMPLETE - DRONE LANDED ✅            ║')
        self.logger.info('╚══════════════════════════════════════════════════════════╝')
        self.control_timer.cancel()
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def transition_to(self, new_state: MissionState):
        """Transition to new state with logging"""
        self.logger.info(f'🔄 STATE CHANGE: {self.current_state.name} → {new_state.name}')
        self.logger.info('─' * 58)
        self.current_state = new_state
        self.state_start_time = time.time()
        
        # Reset circling log control when entering CIRCLING state
        if new_state == MissionState.CIRCLING:
            self.last_logged_circle_segment = -1
    
    def generate_square_waypoints(self):
        """Generate waypoints for current square size - centered around home position"""
        half_size = self.current_square_size / 2
        
        # Use HOME position as center (not current position!)
        if self.home_position is None:
            center_x = self.gt_pose.position.x
            center_y = self.gt_pose.position.y
        else:
            center_x = self.home_position.x
            center_y = self.home_position.y
        
        z = self.config.SEARCH_ALTITUDE
        
        # Square waypoints: 4 corners centered around home
        self.square_waypoints = [
            (center_x + half_size, center_y + half_size, z),  # NE
            (center_x + half_size, center_y - half_size, z),  # SE
            (center_x - half_size, center_y - half_size, z),  # SW
            (center_x - half_size, center_y + half_size, z),  # NW
        ]
        
        self.current_waypoint_idx = 0
    
    def distance_to_point(self, point):
        """Calculate 3D distance to point (x, y, z)"""
        pos = self.gt_pose.position
        return math.sqrt(
            (pos.x - point[0])**2 +
            (pos.y - point[1])**2 +
            (pos.z - point[2])**2
        )
    
    def move_to_position_pid(self, target_x, target_y, target_z):
        """
        Move to position using PID control (closed-loop, slower and more precise)
        Returns: distance to target
        """
        # Get current position
        current_x = self.gt_pose.position.x
        current_y = self.gt_pose.position.y
        current_z = self.gt_pose.position.z
        
        # Calculate errors
        error_x = target_x - current_x
        error_y = target_y - current_y
        error_z = target_z - current_z
        
        # Distance to target
        distance = math.sqrt(error_x**2 + error_y**2 + error_z**2)
        
        # Compute velocities using PID
        dt = 1.0 / self.config.CONTROL_LOOP_RATE  # Control loop period
        vel_x = self.pid_x.compute(error_x, dt)
        vel_y = self.pid_y.compute(error_y, dt)
        vel_z = self.pid_z.compute(error_z, dt)
        
        # Publish velocity commands
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
        """
        Callback for YOLO detection results
        Implements N-consecutive-frames confirmation logic
        Now also stores bbox center for accurate positioning
        """
        try:
            data = json.loads(msg.data)
            detected = data.get('detected', False)
            confidence = data.get('confidence', 0.0)
            count = data.get('count', 0)
            bbox_center = data.get('bbox_center', None)  # NEW: {x, y} normalized 0-1
            
            # Add to buffer if above threshold
            if detected and confidence >= self.config.DETECTION_CONFIDENCE_THRESHOLD:
                self.detection_buffer.append(confidence)
                
                # Store latest bbox center for position calculation
                if bbox_center:
                    self.detection_bbox_center = bbox_center
                
                # Keep buffer size limited
                max_buffer = self.config.DETECTION_CONSECUTIVE_FRAMES + 5
                if len(self.detection_buffer) > max_buffer:
                    self.detection_buffer = self.detection_buffer[-max_buffer:]
                
                # Check if last N frames all have detection
                if len(self.detection_buffer) >= self.config.DETECTION_CONSECUTIVE_FRAMES:
                    last_n = self.detection_buffer[-self.config.DETECTION_CONSECUTIVE_FRAMES:]
                    if all(c >= self.config.DETECTION_CONFIDENCE_THRESHOLD for c in last_n):
                        if not self.human_detected_confirmed:
                            avg_conf = sum(last_n) / len(last_n)
                            self.logger.info(f'🎯 HUMAN CONFIRMED! (avg confidence: {avg_conf:.2f}, '
                                           f'{count} detections)')
                            self.human_detected_confirmed = True
            else:
                # Clear buffer on missed detection (strict consecutive requirement)
                if self.detection_buffer:
                    self.detection_buffer.clear()
                    
        except Exception as e:
            self.logger.error(f'Detection callback error: {e}')


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
def main(args=None):
    rclpy.init(args=args)
    mission = DroneSearchMission()
    
    try:
        rclpy.spin(mission)
    except KeyboardInterrupt:
        mission.logger.info('🛑 Mission interrupted by user')
    finally:
        mission.land()
        mission.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
