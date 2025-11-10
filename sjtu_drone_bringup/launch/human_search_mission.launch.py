#!/usr/bin/env python3
"""
Complete Human Search Mission Launch File
Single command to launch: Gazebo + Drone + YOLO Detector + Mission Controller
"""

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    
    # Get package directories
    bringup_pkg = get_package_share_directory('sjtu_drone_bringup')
    
    return LaunchDescription([
        
        # 1. Launch Gazebo + Drone
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(bringup_pkg, 'launch', 'sjtu_drone_bringup.launch.py')
            )
        ),
        
        # 2. Wait for Gazebo to initialize (8 seconds)
        TimerAction(
            period=8.0,
            actions=[
                # Launch YOLO detector
                Node(
                    package='sjtu_drone_camera',
                    executable='detect_object_by_yolo',
                    name='yolo_detector',
                    output='screen',
                    parameters=[{
                        'target_class_name': 'human',
                        'conf': 0.25
                    }]
                ),
            ]
        ),
        
        # 3. Wait additional 3 seconds for YOLO to load
        TimerAction(
            period=11.0,
            actions=[
                # Launch Mission Controller
                Node(
                    package='sjtu_drone_control',
                    executable='drone_search_mission',
                    name='search_mission',
                    namespace='/simple_drone',
                    output='screen'
                ),
            ]
        ),
    ])
