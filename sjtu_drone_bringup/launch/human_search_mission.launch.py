#!/usr/bin/env python3
"""
Single launch: Gazebo + Drone + YOLO Detector + Mission Controller
"""

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os
import logging


def _set_root_log_level(context, *args, **kwargs):
    # set the root logger level for the launch process
    logging.root.setLevel(logging.INFO)
    return []

def generate_launch_description():

    logging.root.setLevel(logging.FATAL)
    bringup_pkg = get_package_share_directory('sjtu_drone_bringup')
    
    return LaunchDescription([
        
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(bringup_pkg, 'launch', 'sjtu_drone_bringup.launch.py')
            )
        ),
        
        TimerAction(
            period=8.0,
            actions=[
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

        TimerAction(
            period=10.0,
            actions=[
                OpaqueFunction(function=_set_root_log_level),
            ],
        ),

        TimerAction(
            period=11.0,
            actions=[
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
