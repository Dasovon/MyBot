#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import BatteryState
import smbus2

INA219_ADDR = 0x40
REG_CONFIG       = 0x00
REG_SHUNTVOLTAGE = 0x01
REG_BUSVOLTAGE   = 0x02

# Default config: 32V range, PGA/8 (±320mV shunt), 12-bit, continuous
CONFIG_DEFAULT = 0x399F
# 0.1Ω onboard shunt resistor on ACEIRMC INA219 breakout
SHUNT_OHMS = 0.1


class INA219Node(Node):
    def __init__(self):
        super().__init__('ina219')
        self.pub = self.create_publisher(BatteryState, '/battery_state', 10)
        self.bus = smbus2.SMBus(1)
        self._write_word(REG_CONFIG, CONFIG_DEFAULT)
        self.create_timer(1.0, self._publish)
        self.get_logger().info('INA219 node started (addr 0x40, bus 1)')

    def _write_word(self, reg, value):
        self.bus.write_i2c_block_data(INA219_ADDR, reg, [(value >> 8) & 0xFF, value & 0xFF])

    def _read_word(self, reg):
        d = self.bus.read_i2c_block_data(INA219_ADDR, reg, 2)
        return (d[0] << 8) | d[1]

    def _read_signed(self, reg):
        v = self._read_word(reg)
        return v - 65536 if v > 32767 else v

    def _bus_voltage(self):
        # bits [15:3], LSB = 4mV
        return (self._read_word(REG_BUSVOLTAGE) >> 3) * 0.004

    def _current(self):
        # shunt voltage LSB = 10µV; current = V_shunt / R_shunt
        return self._read_signed(REG_SHUNTVOLTAGE) * 10e-6 / SHUNT_OHMS

    def _publish(self):
        try:
            voltage = self._bus_voltage()
            current = self._current()
        except Exception as e:
            self.get_logger().warn(f'INA219 read error: {e}')
            return

        msg = BatteryState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.voltage = float(voltage)
        msg.current = float(current)
        msg.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_DISCHARGING
        msg.power_supply_health = BatteryState.POWER_SUPPLY_HEALTH_GOOD
        msg.power_supply_technology = BatteryState.POWER_SUPPLY_TECHNOLOGY_UNKNOWN
        msg.present = True
        self.pub.publish(msg)


def main():
    rclpy.init()
    node = INA219Node()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
