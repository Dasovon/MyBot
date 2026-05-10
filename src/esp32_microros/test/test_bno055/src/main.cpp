#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <ArduinoOTA.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BNO055.h>
#include "credentials.h"

// ESP32-S3-DevKitC-1 — GPIO22 not exposed; use default I2C pins
#define I2C_SDA 8
#define I2C_SCL 9

static Adafruit_BNO055 bno(55, 0x28, &Wire);

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

    ArduinoOTA.onStart([]() {
        Serial.println("[OTA] Starting update...");
    });
    ArduinoOTA.onEnd([]() {
        Serial.println("\n[OTA] Done. Rebooting.");
    });
    ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
        Serial.printf("[OTA] %u%%\r", progress * 100 / total);
    });
    ArduinoOTA.onError([](ota_error_t error) {
        Serial.printf("[OTA] Error[%u]\n", error);
    });

    ArduinoOTA.begin();
    Serial.println("[OTA] Ready — hostname: esp32-mybot");
}

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== BNO055 Test ===");

    wifi_setup();
    ota_setup();

    Serial.println("Wiring: Vin→3V3  GND→GND  SDA→GPIO8  SCL→GPIO9");
    Wire.begin(I2C_SDA, I2C_SCL);

    if (!bno.begin()) {
        Serial.println("[!!] BNO055 not found on I2C bus");
        Serial.println("     Check: 3V3 present? SDA/SCL swapped? Address conflict?");
        Serial.println("     Retrying every 2s...");
        while (true) {
            ArduinoOTA.handle();  // keep OTA alive even during sensor retry
            delay(2000);
            if (bno.begin()) break;
            Serial.println("[!!] Still not found");
        }
    }

    bno.setExtCrystalUse(true);
    Serial.println("[OK] BNO055 found");
    Serial.println();
    Serial.println("Calibration: S=System G=Gyro A=Accel M=Mag  (0=uncal, 3=fully cal)");
    Serial.println("Gyro calibrates at rest. Move sensor in figure-8 for mag.");
    Serial.println();
    Serial.println("         Quaternion (x,y,z,w)              Gyro (rad/s)            LinearAccel (m/s²)        Cal");
}

void loop() {
    ArduinoOTA.handle();

    uint8_t s, g, a, m;
    bno.getCalibration(&s, &g, &a, &m);

    imu::Quaternion   q  = bno.getQuat();
    imu::Vector<3>    av = bno.getVector(Adafruit_BNO055::VECTOR_GYROSCOPE);
    imu::Vector<3>    la = bno.getVector(Adafruit_BNO055::VECTOR_LINEARACCEL);

    bool cal_ok = (g >= 1 && a >= 1);

    Serial.printf("%s Q(%6.3f %6.3f %6.3f %6.3f)  G(%6.3f %6.3f %6.3f)  A(%6.3f %6.3f %6.3f)  S%dG%dA%dM%d\n",
        cal_ok ? "[OK]" : "[~~]",
        q.x(), q.y(), q.z(), q.w(),
        av.x(), av.y(), av.z(),
        la.x(), la.y(), la.z(),
        s, g, a, m);

    delay(500);
}
