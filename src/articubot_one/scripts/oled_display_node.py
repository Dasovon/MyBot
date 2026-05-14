#!/usr/bin/env python3
import math
import socket
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from sensor_msgs.msg import BatteryState
from nav_msgs.msg import Odometry
from action_msgs.msg import GoalStatusArray, GoalStatus

try:
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1309
    from PIL import Image, ImageDraw, ImageFont
    DISPLAY_AVAILABLE = True
except ImportError:
    DISPLAY_AVAILABLE = False

FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_SIZE = 11
AGENT_TIMEOUT = 3.0

BEST_EFFORT_QOS = QoSProfile(
    depth=10,
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
)


class OledDisplayNode(Node):
    def __init__(self):
        super().__init__('oled_display')

        self._device = None
        self._font = None
        self._init_display()

        self._battery_voltage = None
        self._battery_current = None
        self._vel_linear = None
        self._vel_angular = None
        self._pos_x = None
        self._pos_y = None
        self._pos_yaw = None
        self._last_odom_t = 0.0
        self._nav_status = 'UNKNOWN'

        self.create_subscription(BatteryState, '/battery_state', self._battery_cb, BEST_EFFORT_QOS)
        self.create_subscription(Odometry, '/diff_cont/odom', self._drive_odom_cb, BEST_EFFORT_QOS)
        self.create_subscription(Odometry, '/odom', self._ekf_odom_cb, BEST_EFFORT_QOS)
        self.create_subscription(GoalStatusArray, '/navigate_to_pose/_action/status', self._nav_cb, 10)

        self.create_timer(0.5, self._render)
        self.get_logger().info('OLED display node started')

    def _init_display(self):
        if not DISPLAY_AVAILABLE:
            self.get_logger().warn('luma.oled not installed — display disabled')
            return
        try:
            serial = i2c(port=1, address=0x3C, gpio_RST=27)
            self._device = ssd1309(serial)
            self._font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
        except Exception as e:
            self.get_logger().warn(f'Display init failed: {e}')

    def _battery_cb(self, msg):
        self._battery_voltage = msg.voltage
        self._battery_current = msg.current

    def _drive_odom_cb(self, msg):
        self._last_odom_t = time.monotonic()
        self._vel_linear = msg.twist.twist.linear.x
        self._vel_angular = msg.twist.twist.angular.z

    def _ekf_odom_cb(self, msg):
        self._pos_x = msg.pose.pose.position.x
        self._pos_y = msg.pose.pose.position.y
        q = msg.pose.pose.orientation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                         1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        self._pos_yaw = math.degrees(yaw)

    def _nav_cb(self, msg):
        if not msg.status_list:
            self._nav_status = 'IDLE'
            return
        s = msg.status_list[-1].status
        if s == GoalStatus.STATUS_EXECUTING:
            self._nav_status = 'NAVIGATING'
        elif s == GoalStatus.STATUS_SUCCEEDED:
            self._nav_status = 'SUCCEEDED'
        elif s in (GoalStatus.STATUS_CANCELED, GoalStatus.STATUS_ABORTED):
            self._nav_status = 'IDLE'
        else:
            self._nav_status = 'IDLE'

    def _status_line(self):
        if self._last_odom_t == 0.0 or (time.monotonic() - self._last_odom_t) > AGENT_TIMEOUT:
            return '✗ AGENT OFFLINE'
        if self._nav_status == 'NAVIGATING':
            return '● NAVIGATING'
        if self._nav_status == 'SUCCEEDED':
            return '✓ GOAL REACHED'
        if self._nav_status == 'UNKNOWN':
            return '● TELEOP'
        return '● IDLE'

    def _render(self):
        if self._device is None:
            return

        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = '?.?.?.?'

        bat = (f'{self._battery_voltage:.1f}V  {self._battery_current:.2f}A'
               if self._battery_voltage is not None else '--')
        vel = (f'{self._vel_linear:.2f}m/s  {self._vel_angular:.1f}r/s'
               if self._vel_linear is not None else '--')
        pos = (f'x={self._pos_x:.2f} y={self._pos_y:.2f} {self._pos_yaw:.0f}°'
               if self._pos_x is not None else '--')

        img = Image.new('1', (self._device.width, self._device.height), 0)
        draw = ImageDraw.Draw(img)
        f = self._font

        draw.text((0,  0), f'MyBot  {ip}', font=f, fill=1)
        draw.text((0, 13), f'BAT {bat}', font=f, fill=1)
        draw.text((0, 26), f'VEL {vel}', font=f, fill=1)
        draw.text((0, 39), f'POS {pos}', font=f, fill=1)
        draw.text((0, 52), self._status_line(), font=f, fill=1)

        try:
            self._device.display(img)
        except Exception as e:
            self.get_logger().warn(f'Display render error: {e}')


def main():
    rclpy.init()
    node = OledDisplayNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
