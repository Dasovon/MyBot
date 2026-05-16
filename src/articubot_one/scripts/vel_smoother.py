#!/usr/bin/env python3
"""
Velocity smoother — replicates diff_drive_controller acceleration limiting.

Subscribes to /cmd_vel_raw (twist_mux output), applies configurable
linear/angular acceleration limits, and publishes smooth commands to
/diff_cont/cmd_vel_unstamped at a fixed rate.

This restores the smoothing that diff_drive_controller provided when
the Arduino stack was in use. Without it, step commands from teleop
reach the ESP32 PID directly, causing startup punch and jerk.

Parameters
----------
linear_accel  : float  max linear acceleration  (m/s²), default 0.5
angular_accel : float  max angular acceleration (rad/s²), default 1.0
freq          : float  publish rate (Hz), default 50.0
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from geometry_msgs.msg import Twist


class VelSmoother(Node):
    def __init__(self):
        super().__init__('vel_smoother')
        self.declare_parameter('linear_accel', 0.5)
        self.declare_parameter('angular_accel', 1.0)
        self.declare_parameter('freq', 50.0)

        self._lin_accel = self.get_parameter('linear_accel').value
        self._ang_accel = self.get_parameter('angular_accel').value
        freq = self.get_parameter('freq').value

        self._target_lin = 0.0
        self._target_ang = 0.0
        self._smooth_lin = 0.0
        self._smooth_ang = 0.0

        _best_effort_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self._sub = self.create_subscription(
            Twist, 'cmd_vel_raw', self._cmd_cb, 10)
        self._pub = self.create_publisher(
            Twist, '/diff_cont/cmd_vel_unstamped', _best_effort_qos)

        self._dt = 1.0 / freq
        self._timer = self.create_timer(self._dt, self._tick)

    def _cmd_cb(self, msg: Twist):
        self._target_lin = msg.linear.x
        self._target_ang = msg.angular.z

    def _tick(self):
        dt = self._dt

        # Snap to zero on stop — crisp stop, no coast
        if abs(self._target_lin) < 0.001 and abs(self._target_ang) < 0.001:
            self._smooth_lin = 0.0
            self._smooth_ang = 0.0
        else:
            delta_lin = self._target_lin - self._smooth_lin
            delta_ang = self._target_ang - self._smooth_ang
            limit_lin = self._lin_accel * dt
            limit_ang = self._ang_accel * dt
            self._smooth_lin += max(-limit_lin, min(limit_lin, delta_lin))
            self._smooth_ang += max(-limit_ang, min(limit_ang, delta_ang))

        out = Twist()
        out.linear.x = self._smooth_lin
        out.angular.z = self._smooth_ang
        self._pub.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = VelSmoother()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
