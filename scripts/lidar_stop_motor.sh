#!/usr/bin/env bash
# Stop the RPLIDAR A1M8 motor via the /stop_motor ROS2 service.
#
# The A1M8 has a separate 5V_MOTO power rail (driven by CP2102 DTR by default).
# The motor starts spinning as soon as USB is plugged in and does NOT stop when
# the serial port is closed or the node exits. The only supported software path
# to stop it is the /stop_motor service provided by rplidar_node.
#
# Usage:
#   ./scripts/lidar_stop_motor.sh
#
# Can be run from the dev machine via: ssh ryan@mybot 'bash -s' < scripts/lidar_stop_motor.sh
# Or copied to the Pi and run directly.

set -e

source /opt/ros/humble/setup.bash
source /home/ryan/mybot_ws/install/setup.bash

# Start rplidar_node in background. The node must be running to expose the service.
ros2 run rplidar_ros rplidar_node \
    --ros-args -p serial_port:=/dev/rplidar -p serial_baudrate:=115200 &
NODE_PID=$!

# Wait for node + motor to fully initialize.
# If called too soon the node returns error 80008002 (RESULT_OPERATION_NOT_SUPPORT).
echo "Waiting 12s for rplidar_node to initialize..."
sleep 12

# Send the stop command.
ros2 service call /stop_motor std_srvs/srv/Empty {}
sleep 1

# Tear down the node cleanly.
kill "$NODE_PID" 2>/dev/null || true
wait "$NODE_PID" 2>/dev/null || true

echo "Lidar motor stopped."
