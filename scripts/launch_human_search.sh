#!/bin/bash
cd ~/sim_ws
source install/setup.bash

export GAZEBO_VERBOSITY=0 

ros2 launch sjtu_drone_bringup human_search_mission.launch.py
