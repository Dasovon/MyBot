#!/usr/bin/env python3
import os
import re
import socket
import subprocess
import telnetlib
import threading
import time

DC_PIN = 25
RST_PIN = 27
WIDTH = 128
HEIGHT = 64

ESP32_HOST = os.environ.get('OLED_ESP32_HOST', 'esp32-mybot.local')
ESP32_PORT = int(os.environ.get('OLED_ESP32_PORT', '23'))
BATTERY_LINE_RE = re.compile(r'\[bat\]\s+(?P<v>\d+(?:\.\d+)?)V\s+(?P<i>-?\d+(?:\.\d+)?)A')

DATA_TIMEOUT = 30.0
STALE_STATUS_S = 3.0
RECONNECT_DELAY_S = 2.0

try:
    import spidev
    import RPi.GPIO as GPIO
    from PIL import Image, ImageDraw, ImageFont
    DISPLAY_AVAILABLE = True
except ImportError:
    DISPLAY_AVAILABLE = False


class BatteryFeed:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.voltage = None
        self.current = None
        self.last_update_t = 0.0
        self.link_start_t = 0.0
        self.connected = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2.0)

    def snapshot(self):
        with self._lock:
            return (
                self.voltage,
                self.current,
                self.last_update_t,
                self.link_start_t,
                self.connected,
            )

    def _set(self, voltage=None, current=None, connected=None):
        with self._lock:
            if voltage is not None:
                self.voltage = voltage
            if current is not None:
                self.current = current
            if connected is not None:
                self.connected = connected
                if connected:
                    self.link_start_t = time.monotonic()
                else:
                    self.link_start_t = 0.0
            if voltage is not None or current is not None:
                self.last_update_t = time.monotonic()
                if self.link_start_t == 0.0:
                    self.link_start_t = self.last_update_t

    def _run(self):
        while not self._stop.is_set():
            try:
                self._set(connected=False)
                tn = telnetlib.Telnet(self.host, self.port, timeout=5)
                self._set(connected=True)
                buf = b''
                while not self._stop.is_set():
                    chunk = tn.read_until(b'\n', timeout=1)
                    if chunk:
                        buf += chunk
                        while b'\n' in buf:
                            raw, buf = buf.split(b'\n', 1)
                            self._consume_line(raw.decode('utf-8', errors='ignore'))
                try:
                    tn.close()
                except Exception:
                    pass
            except Exception:
                self._set(connected=False)
                time.sleep(RECONNECT_DELAY_S)

    def _consume_line(self, line: str):
        m = BATTERY_LINE_RE.search(line)
        if not m:
            return
        self._set(voltage=float(m.group('v')), current=float(m.group('i')))


class OledDisplay:
    def __init__(self):
        self._spi = None
        self._feed = BatteryFeed(ESP32_HOST, ESP32_PORT)
        self._node_start_t = time.monotonic()
        self._init_display()

    def close(self):
        try:
            self._feed.stop()
        finally:
            try:
                if self._spi is not None:
                    self._spi.close()
            except Exception:
                pass
            try:
                GPIO.cleanup()
            except Exception:
                pass

    def _cmd(self, c):
        GPIO.output(DC_PIN, GPIO.LOW)
        self._spi.writebytes([c])

    def _init_display(self):
        if not DISPLAY_AVAILABLE:
            print('[oled_display] spidev/RPi.GPIO not installed - display disabled', flush=True)
            return
        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(DC_PIN, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(RST_PIN, GPIO.OUT, initial=GPIO.LOW)

            self._spi = spidev.SpiDev()
            self._spi.open(0, 0)
            self._spi.max_speed_hz = 100000
            self._spi.mode = 0b11

            self._spi.writebytes([0x00])
            time.sleep(0.1)
            self._spi.close()
            self._spi.open(0, 0)
            self._spi.max_speed_hz = 100000
            self._spi.mode = 0b11
            time.sleep(0.05)

            time.sleep(0.1)
            GPIO.output(RST_PIN, GPIO.HIGH)
            time.sleep(0.1)
            GPIO.output(RST_PIN, GPIO.LOW)
            time.sleep(0.1)
            GPIO.output(RST_PIN, GPIO.HIGH)
            time.sleep(0.2)

            self._cmd(0xAE)
            self._cmd(0x20); self._cmd(0x02)
            self._cmd(0x40)
            self._cmd(0xA1)
            self._cmd(0xA6)
            self._cmd(0xA8); self._cmd(0x3F)
            self._cmd(0xC8)
            self._cmd(0xD3); self._cmd(0x00)
            self._cmd(0xD5); self._cmd(0x80)
            self._cmd(0xD9); self._cmd(0x22)
            self._cmd(0xDA); self._cmd(0x12)
            self._cmd(0xDB); self._cmd(0x40)
            self._cmd(0x81); self._cmd(0x7F)
            self._cmd(0xAF)
            self._cmd(0xA5)
            time.sleep(1.0)
            self._cmd(0xA4)

            _mono = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
            self._font_big = ImageFont.truetype(_mono, 11)
            self._font_med = ImageFont.truetype(_mono, 9)
            print('[oled_display] Display init OK', flush=True)
        except Exception as e:
            print(f'[oled_display] Display init failed: {e}', flush=True)
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

    def _format_uptime(self, age_s):
        total = max(0, int(age_s))
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        if hours:
            return f'{hours:d}:{minutes:02d}:{seconds:02d}'
        return f'{minutes:02d}:{seconds:02d}'

    def _text_width(self, text):
        return org_text_width(text)

    def _draw_battery_icon(self, draw, x, y, voltage):
        if voltage is None:
            bars = 0
        else:
            bars = int(round((voltage - 9.0) / (12.6 - 9.0) * 4.0))
        bars = max(0, min(4, bars))

        body_w = 22
        body_h = 12
        tip_w = 2
        tip_h = 6
        draw.rectangle((x, y, x + body_w - 1, y + body_h - 1), outline=0, fill=1)
        draw.rectangle((x + body_w, y + 3, x + body_w + tip_w - 1, y + 3 + tip_h - 1), outline=0, fill=1)

        inner_h = body_h - 4
        for idx in range(4):
            bx = x + 2 + idx * 4
            if idx < bars:
                draw.rectangle((bx, y + 2, bx + 2, y + 1 + inner_h), fill=0)
            else:
                draw.rectangle((bx, y + 2, bx + 2, y + 1 + inner_h), outline=0, fill=1)

    def _ros_status(self):
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', 'robot-launch.service'],
                capture_output=True,
                text=True,
                timeout=1.0,
                check=False,
            )
            return 'ROS OK' if result.stdout.strip() == 'active' else 'ROS OFF'
        except Exception:
            return 'ROS OFF'

    def _esp_status(self, connected, battery_voltage, battery_age_s):
        if battery_voltage is None:
            if (time.monotonic() - self._node_start_t) > DATA_TIMEOUT:
                return 'ESP OFF'
            return 'START'
        if battery_age_s <= STALE_STATUS_S or connected:
            return 'ESP OK'
        return 'ESP OFF'

    def render_loop(self):
        while True:
            if self._spi is None:
                time.sleep(2.0)
                continue

            battery_v, battery_a, battery_t, link_t, connected = self._feed.snapshot()
            battery_age_s = (time.monotonic() - battery_t) if battery_t else 999.0
            link_age_s = (time.monotonic() - link_t) if link_t else 0.0

            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(('8.8.8.8', 80))
                ip = s.getsockname()[0]
                s.close()
            except Exception:
                ip = '?.?.?.?'

            bat_voltage = f'{battery_v:.1f}V' if battery_v is not None else '--'
            current_text = f'{battery_a:.2f}A' if battery_v is not None else '--'
            esp_status = self._esp_status(connected, battery_v, battery_age_s)
            ros_status = self._ros_status()
            uptime_text = self._format_uptime(link_age_s)

            img = Image.new('1', (WIDTH, HEIGHT), 1)
            draw = ImageDraw.Draw(img)

            draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline=0, fill=1)
            draw.line((0, 16, WIDTH - 1, 16), fill=0)
            draw.line((0, 32, WIDTH - 1, 32), fill=0)
            draw.line((0, 48, WIDTH - 1, 48), fill=0)

            fb = self._font_big
            fm = self._font_med

            def rw(text, font):
                return int(draw.textlength(text, font=font))

            # Row 1: battery icon + voltage left, current right (11pt, centred in 16px row)
            self._draw_battery_icon(draw, 4, 4, battery_v)
            draw.text((31, 2),                             bat_voltage,  font=fb, fill=0)
            draw.text((122 - rw(current_text, fb), 2),    current_text, font=fb, fill=0)

            # Row 2: IP label left, address right (9pt, centred)
            draw.text((4, 20),                             'IP',         font=fm, fill=0)
            draw.text((122 - rw(ip, fm), 20),             ip,           font=fm, fill=0)

            # Row 3: ROS status left, ESP status right (9pt, centred)
            draw.text((3, 36),                             ros_status,   font=fm, fill=0)
            draw.text((122 - rw(esp_status, fm), 36),     esp_status,   font=fm, fill=0)

            # Row 4: UPTIME left, time right (9pt, centred)
            draw.text((3, 52),                             'UPTIME',     font=fm, fill=0)
            draw.text((122 - rw(uptime_text, fm), 52),    uptime_text,  font=fm, fill=0)

            try:
                self._show(img)
            except Exception as e:
                print(f'[oled_display] Display render error: {e}', flush=True)

            if battery_v is None and (time.monotonic() - self._node_start_t) > DATA_TIMEOUT:
                print('[oled_display] No ESP32 battery data in 30s - restarting to renegotiate', flush=True)
                os._exit(1)

            time.sleep(0.5)


def main():
    display = OledDisplay()
    try:
        display.render_loop()
    except KeyboardInterrupt:
        pass
    finally:
        display.close()


if __name__ == '__main__':
    main()
