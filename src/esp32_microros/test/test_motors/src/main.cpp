#include <Arduino.h>

// TB6612 pins — Motor A = RIGHT, Motor B = LEFT — ESP32-S3-DevKitC-1
#define PWMA  1
#define AIN1  2
#define AIN2  4
#define PWMB  5
#define BIN1  6
#define BIN2  7

static void motor_set(uint8_t pwm_pin, uint8_t in1, uint8_t in2, int spd) {
    if      (spd > 0) { digitalWrite(in1, HIGH); digitalWrite(in2, LOW);  }
    else if (spd < 0) { digitalWrite(in1, LOW);  digitalWrite(in2, HIGH); spd = -spd; }
    else              { digitalWrite(in1, LOW);  digitalWrite(in2, LOW);  }
    ledcWrite(pwm_pin, (uint32_t)constrain(spd, 0, 255));
}

static void stop_all() {
    motor_set(PWMB, BIN1, BIN2, 0);
    motor_set(PWMA, AIN1, AIN2, 0);
}

static void run_sequence() {
    Serial.println("\n--- Left motor forward 2s (BIN2=HIGH) ---");
    motor_set(PWMB, BIN1, BIN2, 150); delay(2000); stop_all(); delay(500);

    Serial.println("--- Left motor reverse 2s (BIN1=HIGH) ---");
    motor_set(PWMB, BIN1, BIN2, -150); delay(2000); stop_all(); delay(500);

    Serial.println("--- Right motor forward 2s (AIN2=HIGH) ---");
    motor_set(PWMA, AIN1, AIN2, 150); delay(2000); stop_all(); delay(500);

    Serial.println("--- Right motor reverse 2s (AIN1=HIGH) ---");
    motor_set(PWMA, AIN1, AIN2, -150); delay(2000); stop_all(); delay(500);

    Serial.println("--- Both forward: PWM ramp 0→200→0 ---");
    for (int s = 0; s <= 200; s += 20) {
        motor_set(PWMB, BIN1, BIN2, s);
        motor_set(PWMA, AIN1, AIN2, s);
        Serial.printf("  PWM %3d\n", s);
        delay(150);
    }
    for (int s = 200; s >= 0; s -= 20) {
        motor_set(PWMB, BIN1, BIN2, s);
        motor_set(PWMA, AIN1, AIN2, s);
        delay(150);
    }
    stop_all();

    Serial.println("\nSequence done. Manual control active.");
    Serial.println("f=both fwd  b=both rev  l=left fwd  r=right fwd  s=stop");
}

void setup() {
    Serial.begin(115200);
    delay(500);

    pinMode(AIN1, OUTPUT); pinMode(AIN2, OUTPUT);
    pinMode(BIN1, OUTPUT); pinMode(BIN2, OUTPUT);
    ledcAttach(PWMA, 1000, 8);
    ledcAttach(PWMB, 1000, 8);
    stop_all();

    Serial.println("\n=== Motor Test ===");
    Serial.println("BEFORE STARTING:");
    Serial.println("  1. Confirm replacement TB6612 is installed");
    Serial.println("  2. Verify 12V VM wire is NOT bridged to AIN1 or BIN1");
    Serial.println("  3. Robot should be on blocks — wheels will spin");
    Serial.println();
    Serial.println("Expected directions (looking at robot from above):");
    Serial.println("  Left  forward  = CCW rotation (BIN2=HIGH)");
    Serial.println("  Right forward  = CW  rotation (AIN2=HIGH)");
    Serial.println("  If reversed: swap motor output wires at TB6612 terminal");
    Serial.println();
    Serial.println("Send 'g' to run test sequence");
}

void loop() {
    if (!Serial.available()) return;
    char c = Serial.read();
    switch (c) {
        case 'g': run_sequence(); break;
        case 'f':
            motor_set(PWMB, BIN1, BIN2,  150);
            motor_set(PWMA, AIN1, AIN2,  150);
            Serial.println("Both forward");  break;
        case 'b':
            motor_set(PWMB, BIN1, BIN2, -150);
            motor_set(PWMA, AIN1, AIN2, -150);
            Serial.println("Both reverse");  break;
        case 'l':
            motor_set(PWMB, BIN1, BIN2,  150);
            motor_set(PWMA, AIN1, AIN2,    0);
            Serial.println("Left forward only");  break;
        case 'r':
            motor_set(PWMB, BIN1, BIN2,    0);
            motor_set(PWMA, AIN1, AIN2,  150);
            Serial.println("Right forward only"); break;
        case 's':
            stop_all();
            Serial.println("Stopped"); break;
    }
}
