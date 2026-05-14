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
    import spidev
    import RPi.GPIO as GPIO
    from PIL import Image, ImageDraw, ImageFont
    DISPLAY_AVAILABLE = True
except ImportError:
    DISPLAY_AVAILABLE = False

FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_SIZE = 11
AGENT_TIMEOUT = 3.0
DC_PIN = 25
RST_PIN = 27
WIDTH = 128
HEIGHT = 64

BEST_EFFORT_QOS = QoSProfile(
    depth=10,
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
)


class OledDisplayNode(Node):
    def __init__(self):
        super().__init__('oled_display')

        self._spi = None
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

    def _cmd(self, c):
        GPIO.output(DC_PIN, GPIO.LOW)
        self._spi.writebytes([c])

    def _init_display(self):
        if not DISPLAY_AVAILABLE:
            self.get_logger().warn('spidev/RPi.GPIO not installed — display disabled')
            return
        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(DC_PIN, GPIO.OUT, initial=GPIO.LOW)
            # Drive RST LOW before opening SPI — holds display in reset while
            # the SPI clock line transitions to its idle state (HIGH for mode 3),
            # preventing spurious commands from reaching the SSD1309 on first boot.
            GPIO.setup(RST_PIN, GPIO.OUT, initial=GPIO.LOW)

            self._spi = spidev.SpiDev()
            self._spi.open(0, 0)
            self._spi.max_speed_hz = 1000000
            self._spi.mode = 0b11

            # Hardware reset — RST is already LOW from setup above
            time.sleep(0.1)                       # hold in reset
            GPIO.output(RST_PIN, GPIO.HIGH); time.sleep(0.1)
            GPIO.output(RST_PIN, GPIO.LOW);  time.sleep(0.1)
            GPIO.output(RST_PIN, GPIO.HIGH); time.sleep(0.2)  # longer settle

            # SSD1309 init sequence
            self._cmd(0xAE)
            self._cmd(0x00); self._cmd(0x10)
            self._cmd(0x20); self._cmd(0x00)
            self._cmd(0xFF)
            self._cmd(0xA6)
            self._cmd(0xA8); self._cmd(0x3F)
            self._cmd(0xD3); self._cmd(0x00)
            self._cmd(0xD5); self._cmd(0x80)
            self._cmd(0xD9); self._cmd(0x22)
            self._cmd(0xDA); self._cmd(0x12)
            self._cmd(0xDB); self._cmd(0x40)
            time.sleep(0.1)
            self._cmd(0xAF)

            self._font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
            self.get_logger().info('Display init OK')
        except Exception as e:
            self.get_logger().warn(f'Display init failed: {e}')
            self._spi = None

    def _show(self, image):
        pixels = image.convert('1').load()
        for page in range(8):
            self._cmd(0xB0 + page)
            self._cmd(0x00)
            self._cmd(0x10)
            GPIO.output(DC_PIN, GPIO.HIGH)
            row = []
            for x in range(WIDTH):
                byte = 0xFF
                for bit in range(8):
                    y = page * 8 + bit
                    if pixels[x, y] == 0:
                        byte &= ~(1 << bit)
                row.append(~byte & 0xFF)
            self._spi.writebytes(row)

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
            return 'AGENT OFFLINE'
        if self._nav_status == 'NAVIGATING':
            return 'NAVIGATING'
        if self._nav_status == 'SUCCEEDED':
            return 'GOAL REACHED'
        if self._nav_status == 'UNKNOWN':
            return 'TELEOP'
        return 'IDLE'

    def _render(self):
        if self._spi is None:
            return

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            ip = '?.?.?.?'

        bat = (f'{self._battery_voltage:.1f}V  {self._battery_current:.2f}A'
               if self._battery_voltage is not None else '--')
        vel = (f'{self._vel_linear:.2f}m/s  {self._vel_angular:.1f}r/s'
               if self._vel_linear is not None else '--')
        pos = (f'x={self._pos_x:.2f} y={self._pos_y:.2f} {self._pos_yaw:.0f}d'
               if self._pos_x is not None else '--')

        # White background (off), black text (lit) — matches SSD1309 pixel convention
        img = Image.new('1', (WIDTH, HEIGHT), 1)
        draw = ImageDraw.Draw(img)
        f = self._font

        draw.text((4,  0), f'MyBot  {ip}', font=f, fill=0)
        draw.text((4, 13), f'BAT {bat}', font=f, fill=0)
        draw.text((4, 26), f'VEL {vel}', font=f, fill=0)
        draw.text((4, 39), f'POS {pos}', font=f, fill=0)
        draw.text((4, 52), self._status_line(), font=f, fill=0)

        try:
            self._show(img)
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
