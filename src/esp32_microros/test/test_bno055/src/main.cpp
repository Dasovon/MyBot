#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BNO055.h>

// ESP32 DevKitC V4 — hardware I2C pins
#define I2C_SDA 21
#define I2C_SCL 22

Adafruit_BNO055 bno(55, 0x28, &Wire);

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n=== BNO055 Test ===");

    Wire.begin(I2C_SDA, I2C_SCL);

    if (!bno.begin()) {
        Serial.println("[!!] BNO055 not found on I2C bus");
        Serial.println("     Check wiring: SDA->GPIO21, SCL->GPIO22, 3.3V, GND");
        Serial.println("     Retrying every 2s...");
        while (true) {
            delay(2000);
            if (bno.begin()) break;
            Serial.println("     still not found...");
        }
    }

    bno.setExtCrystalUse(true);
    Serial.println("[OK] BNO055 found");

    adafruit_bno055_offsets_t offsets;
    bno.getSensorOffsets(offsets);
    Serial.printf("     Accel offsets: x=%d y=%d z=%d\n",
        offsets.accel_offset_x, offsets.accel_offset_y, offsets.accel_offset_z);
    Serial.println("     Printing euler angles every 500ms...\n");
}

void loop() {
    uint8_t sys, gyro, accel, mag;
    bno.getCalibration(&sys, &gyro, &accel, &mag);

    imu::Vector<3> euler = bno.getVector(Adafruit_BNO055::VECTOR_EULER);

    Serial.printf("Heading: %6.1f  Roll: %6.1f  Pitch: %6.1f  | Calib sys=%d gyro=%d accel=%d mag=%d\n",
        euler.x(), euler.z(), euler.y(),
        sys, gyro, accel, mag);

    delay(500);
}
