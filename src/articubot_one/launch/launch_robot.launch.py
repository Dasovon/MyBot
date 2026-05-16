import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch.launch_description_sources import PythonLaunchDescriptionSource

from launch_ros.actions import Node


def generate_launch_description():

    package_name = 'articubot_one'
    esp32_serial = '/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_58:E6:C5:5C:23:1C-if00'
    enable_lidar = LaunchConfiguration('enable_lidar')
    enable_camera = LaunchConfiguration('enable_camera')
    enable_motion = LaunchConfiguration('enable_motion')

    rsp = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory(package_name), 'launch', 'rsp.launch.py'
                )]), launch_arguments={'use_sim_time': 'false', 'use_ros2_control': 'true'}.items()
    )

    twist_mux_params = os.path.join(get_package_share_directory(package_name), 'config', 'twist_mux.yaml')
    twist_mux = Node(
            package="twist_mux",
            executable="twist_mux",
            parameters=[twist_mux_params],
            remappings=[('/cmd_vel_out', '/cmd_vel_raw')],
            condition=IfCondition(enable_motion),
        )

    # Motion is opt-in. The bridge and battery/status stack can run at boot
    # without any drive commands being forwarded to the ESP32.
    vel_smoother = Node(
        package='articubot_one',
        executable='vel_smoother.py',
        parameters=[{'linear_accel': 0.5, 'angular_accel': 1.0, 'freq': 50.0}],
        condition=IfCondition(enable_motion),
    )

    micro_ros_agent = Node(
        package='micro_ros_agent',
        executable='micro_ros_agent',
        arguments=['serial', '--dev', esp32_serial],
        output='screen',
    )

    lidar = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory(package_name), 'launch', 'rplidar.launch.py'
                )]),
                condition=IfCondition(enable_lidar),
    )

    camera = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory(package_name), 'launch', 'camera.launch.py'
                )]),
                condition=IfCondition(enable_camera),
    )

    # NOTE: EKF runs on dev machine via dev_launch.py — fuses /diff_cont/odom + /imu/imu -> /odom
    # ESP32 publishes: /diff_cont/odom, /imu/imu, /battery_state, subscribes: /diff_cont/cmd_vel_unstamped
    # oled_display_node runs as a systemd service (oled-display.service) — starts on boot independently

    return LaunchDescription([
        DeclareLaunchArgument('enable_lidar', default_value='false'),
        DeclareLaunchArgument('enable_camera', default_value='false'),
        DeclareLaunchArgument('enable_motion', default_value='false'),
        rsp,
        micro_ros_agent,
        # Delay the motion path 2s so any optional drive stack comes up after the bridge.
        # The default boot stack keeps motion disabled so the robot stays still on the ground.
        TimerAction(period=2.0, actions=[twist_mux]),
        TimerAction(period=2.0, actions=[vel_smoother]),
        TimerAction(period=8.0, actions=[lidar]),
        camera,
    ])
