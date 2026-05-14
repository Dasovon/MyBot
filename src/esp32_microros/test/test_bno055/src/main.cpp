#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <ArduinoOTA.h>
#include <TelnetStream.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BNO055.h>
#include <Adafruit_INA219.h>
#include "credentials.h"

// ESP32-S3-DevKitC-1 — GPIO22 not exposed; use default I2C pins
#define I2C_SDA 8
#define I2C_SCL 9

static Adafruit_BNO055 bno(55, 0x28, &Wire);
static Adafruit_INA219 ina219(0x40);

template<typename... Args>
static void log(const char* fmt, Args... args) {
    char buf[256];
    snprintf(buf, sizeof(buf), fmt, args...);
    Serial.print(buf);
    TelnetStream.print(buf);
}

static void wifi_setup() {
    Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.printf("\n[WiFi] Connected — IP: %s\n", WiFi.localIP().toString().c_str());
}

static void ota_setup() {
    ArduinoOTA.setHostname("esp32-mybot");
    ArduinoOTA.setPassword(OTA_PASSWORD);
    ArduinoOTA.onStart([]() { log("[OTA] Starting update...\n"); });
    ArduinoOTA.onEnd([]()   { log("[OTA] Done. Rebooting.\n"); });
    ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
        log("[OTA] %u%%\r", progress * 100 / total);
    });
    ArduinoOTA.onError([](ota_error_t error) {
        log("[OTA] Error[%u]\n", error);
    });
    ArduinoOTA.begin();
    Serial.println("[OTA] Ready — hostname: esp32-mybot");
}

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== BNO055 + INA219 Test ===");

    wifi_setup();
    ota_setup();
    TelnetStream.begin();
    Serial.println("[Telnet] Listening on port 23 — connect: nc esp32-mybot.local 23");

    Wire.begin(I2C_SDA, I2C_SCL);
    delay(100);  // let I2C bus settle before probing

    // BNO055
    if (!bno.begin()) {
        log("[!!] BNO055 not found — check wiring. Retrying every 2s...\n");
        while (true) {
            ArduinoOTA.handle();
            delay(2000);
            if (bno.begin()) break;
            log("[!!] BNO055 still not found\n");
        }
    }
    bno.setExtCrystalUse(true);
    log("[OK] BNO055 found (0x28)\n");

    // INA219
    if (!ina219.begin()) {
        log("[!!] INA219 not found (0x40) — retrying every 2s...\n");
        while (true) {
            ArduinoOTA.handle();
            delay(2000);
            if (ina219.begin()) break;
            log("[!!] INA219 still not found\n");
        }
    }
    log("[OK] INA219 found (0x40)\n");

    log("\nCalib: S=System G=Gyro A=Accel M=Mag  (0=uncal 3=fully cal)\n\n");
    log("  Voltage    Current    Power   |  Quaternion (x,y,z,w)                      Cal\n");
}

void loop() {
    ArduinoOTA.handle();

    float voltage = ina219.getBusVoltage_V();
    float current = ina219.getCurrent_mA() / 1000.0f;
    float power   = ina219.getPower_mW()   / 1000.0f;

    uint8_t s, g, a, m;
    bno.getCalibration(&s, &g, &a, &m);
    imu::Quaternion q = bno.getQuat();

    log("%7.3fV  %7.3fA  %6.3fW  |  Q(%6.3f %6.3f %6.3f %6.3f)  S%dG%dA%dM%d\n",
        voltage, current, power,
        q.x(), q.y(), q.z(), q.w(),
        s, g, a, m);

    delay(500);
}
