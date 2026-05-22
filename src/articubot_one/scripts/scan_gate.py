#!/usr/bin/env python3
"""
Drops lidar scans when the robot is spinning fast.
Prevents slam_toolbox from ingesting motion-distorted scans during in-place rotation,
which causes it to jump to a wrong heading and override the accurate EKF/IMU estimate.

Subscribes to /scan and /odom, republishes to /scan_gated only when
|angular_velocity_z| < ANG_VEL_THRESHOLD.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry

ANG_VEL_THRESHOLD = 0.3  # rad/s — drops scans above this (floor_baseline spins at 1.5 rad/s)


class ScanGate(Node):
    def __init__(self):
        super().__init__('scan_gate')
        self._wz = 0.0

        sensor_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )

        self.sub_scan = self.create_subscription(LaserScan, '/scan', self._scan_cb, sensor_qos)
        self.sub_odom = self.create_subscription(Odometry, '/odom', self._odom_cb, 10)
        self.pub = self.create_publisher(LaserScan, '/scan_gated', sensor_qos)

    def _odom_cb(self, msg: Odometry):
        self._wz = msg.twist.twist.angular.z

    def _scan_cb(self, msg: LaserScan):
        if abs(self._wz) < ANG_VEL_THRESHOLD:
            self.pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = ScanGate()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
