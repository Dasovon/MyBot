import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource

from launch_ros.actions import Node


def generate_launch_description():

    package_name = 'articubot_one'

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
            remappings=[('/cmd_vel_out', '/diff_cont/cmd_vel_unstamped')]
        )

    micro_ros_agent = Node(
        package='micro_ros_agent',
        executable='micro_ros_agent',
        arguments=['serial', '--dev', '/dev/ttyACM0'],
        output='screen',
    )

    lidar = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory(package_name), 'launch', 'rplidar.launch.py'
                )])
    )

    camera = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory(package_name), 'launch', 'camera.launch.py'
                )])
    )

    oled = Node(
        package=package_name,
        executable='oled_display_node.py',
    )

    # NOTE: EKF runs on dev machine via dev_launch.py — fuses /diff_cont/odom + /imu/imu -> /odom
    # ESP32 publishes: /diff_cont/odom, /imu/imu, /battery_state, subscribes: /diff_cont/cmd_vel_unstamped

    return LaunchDescription([
        rsp,
        twist_mux,
        micro_ros_agent,
        lidar,
        camera,
        oled,
    ])
