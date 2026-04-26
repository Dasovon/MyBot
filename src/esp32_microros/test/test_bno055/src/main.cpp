#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BNO055.h>

// PASS: lines starting with [OK]
// FAIL: lines starting with [!!]

static Adafruit_BNO055 bno(55, 0x28, &Wire);

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== BNO055 Test ===");
    Serial.println("Wiring: Vin→3V3  GND→GND  SDA→GPIO21  SCL→GPIO22");
    Serial.println("ADR unconnected = address 0x28");

    Wire.begin(21, 22);

    if (!bno.begin()) {
        Serial.println("[!!] BNO055 not found on I2C bus");
        Serial.println("     Check: 3V3 present? SDA/SCL swapped? Address conflict?");
        Serial.println("     Retrying every 2s...");
        while (true) {
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
