import os

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():

    realsense_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            os.path.join(get_package_share_directory('realsense2_camera'), 'launch', 'rs_launch.py')
        ]),
        launch_arguments={
            'camera_namespace':           'camera',
            'camera_name':               'camera',
            'rgb_camera.color_profile':  '640x480x15',
            'depth_module.depth_profile': '640x480x15',
            'enable_pointcloud':         'false',
            'align_depth.enable':        'false',
            'initial_reset':             'true',
            'qos_overrides./camera/camera/color/image_raw.publisher.durability': 'volatile',
            'qos_overrides./camera/camera/depth/image_rect_raw.publisher.durability': 'volatile',
        }.items()
    )

    return LaunchDescription([
        realsense_launch,
    ])
