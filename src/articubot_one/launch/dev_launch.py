import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    """
    Dev machine launch — runs computationally heavy nodes offloaded from Pi.

    Launch sequence on dev machine:
      Terminal 1: ros2 launch articubot_one dev_launch.py
      Terminal 2: ros2 launch articubot_one localization_launch.py
      Terminal 3: ros2 launch articubot_one navigation_launch.py
      Terminal 4: rviz2

    Pi must already be running: ros2 launch articubot_one launch_robot.launch.py
    """

    package_name = 'articubot_one'

    ekf = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        parameters=[os.path.join(get_package_share_directory(package_name), 'config', 'ekf.yaml')],
        remappings=[('/odometry/filtered', '/odom')],
    )

    return LaunchDescription([
        ekf,
    ])
