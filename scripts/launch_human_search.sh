#!/bin/bash
# Quick Start Script - Human Search Mission
# Autonomous drone searching for humans with YOLO v11

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   🚁 DRONE HUMAN SEARCH MISSION - LAUNCHER 🚁          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Starting complete system:"
echo "  1. Gazebo simulator + Drone"
echo "  2. YOLO v11 human detector"
echo "  3. Autonomous mission controller"
echo ""
echo "Mission profile:"
echo "  • Expanding squares: 2m → 20m (+2m each)"
echo "  • Detection threshold: 0.8 (5 consecutive frames)"
echo "  • Circling: 2 rotations @ 3m radius"
echo ""
echo "Press Ctrl+C to abort mission"
echo "─────────────────────────────────────────────────────────"
sleep 2

cd ~/sim_ws
source install/setup.bash

# Suppress Gazebo texture warnings (show only errors)
export GAZEBO_VERBOSITY=0  # 0=none, 1=err(only errors), 2=warn(default), 3=info, 4=debug

# Launch everything
ros2 launch sjtu_drone_bringup human_search_mission.launch.py
