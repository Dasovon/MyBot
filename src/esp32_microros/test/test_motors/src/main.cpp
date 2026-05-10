#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoOTA.h>
#include <TelnetStream.h>
#include "credentials.h"

// TB6612 pins — Motor A = RIGHT, Motor B = LEFT — Lonely Binary ESP32-S3 Expansion Base
#define PWMA     10
#define AIN1     11
#define AIN2     12
#define PWMB     13
#define BIN1     14
#define BIN2     15
#define PWMA_CH  0   // LEDC channel for RIGHT motor
#define PWMB_CH  1   // LEDC channel for LEFT motor

template<typename... Args>
static void log(const char* fmt, Args... args) {
    char buf[256];
    snprintf(buf, sizeof(buf), fmt, args...);
    Serial.print(buf);
    TelnetStream.print(buf);
}

static int read_char() {
    if (Serial.available())       return Serial.read();
    if (TelnetStream.available()) return TelnetStream.read();
    return -1;
}

static void wifi_setup() {
    Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
    Serial.printf("\n[WiFi] Connected — IP: %s\n", WiFi.localIP().toString().c_str());
}

static void ota_setup() {
    ArduinoOTA.setHostname("esp32-mybot");
    ArduinoOTA.setPassword(OTA_PASSWORD);
    ArduinoOTA.onStart([]() { log("[OTA] Starting...\n"); });
    ArduinoOTA.onEnd([]()   { log("[OTA] Done.\n"); });
    ArduinoOTA.onProgress([](unsigned int p, unsigned int t) { log("[OTA] %u%%\r", p*100/t); });
    ArduinoOTA.onError([](ota_error_t e) { log("[OTA] Error[%u]\n", e); });
    ArduinoOTA.begin();
    Serial.println("[OTA] Ready — hostname: esp32-mybot");
}

static void motor_set(uint8_t ch, uint8_t in1, uint8_t in2, int spd) {
    if      (spd > 0) { digitalWrite(in1, HIGH); digitalWrite(in2, LOW);  }
    else if (spd < 0) { digitalWrite(in1, LOW);  digitalWrite(in2, HIGH); spd = -spd; }
    else              { digitalWrite(in1, LOW);  digitalWrite(in2, LOW);  }
    ledcWrite(ch, (uint32_t)constrain(spd, 0, 255));
}

static void stop_all() {
    motor_set(PWMB_CH, BIN1, BIN2, 0);
    motor_set(PWMA_CH, AIN1, AIN2, 0);
}

static void run_sequence() {
    log("\n--- Left motor forward 2s ---\n");
    motor_set(PWMB_CH, BIN1, BIN2,  150); delay(2000); stop_all(); delay(500);

    log("--- Left motor reverse 2s ---\n");
    motor_set(PWMB_CH, BIN1, BIN2, -150); delay(2000); stop_all(); delay(500);

    log("--- Right motor forward 2s ---\n");
    motor_set(PWMA_CH, AIN1, AIN2,  150); delay(2000); stop_all(); delay(500);

    log("--- Right motor reverse 2s ---\n");
    motor_set(PWMA_CH, AIN1, AIN2, -150); delay(2000); stop_all(); delay(500);

    log("--- Both forward: PWM ramp 0→200→0 ---\n");
    for (int s = 0; s <= 200; s += 20) {
        motor_set(PWMB_CH, BIN1, BIN2, s);
        motor_set(PWMA_CH, AIN1, AIN2, s);
        log("  PWM %3d\n", s);
        delay(150);
    }
    for (int s = 200; s >= 0; s -= 20) {
        motor_set(PWMB_CH, BIN1, BIN2, s);
        motor_set(PWMA_CH, AIN1, AIN2, s);
        delay(150);
    }
    stop_all();
    log("\nSequence done. Manual control active.\n");
    log("f=both fwd  b=both rev  l=left fwd  r=right fwd  s=stop\n");
}

void setup() {
    Serial.begin(115200);
    delay(500);

    wifi_setup();
    ota_setup();
    TelnetStream.begin();
    Serial.println("[Telnet] port 23 — connect: nc 192.168.86.43 23");

    pinMode(AIN1, OUTPUT); pinMode(AIN2, OUTPUT);
    pinMode(BIN1, OUTPUT); pinMode(BIN2, OUTPUT);
    ledcSetup(PWMA_CH, 1000, 8); ledcAttachPin(PWMA, PWMA_CH);
    ledcSetup(PWMB_CH, 1000, 8); ledcAttachPin(PWMB, PWMB_CH);
    stop_all();

    log("\n=== Motor Test ===\n");
    log("BEFORE STARTING:\n");
    log("  1. Confirm replacement TB6612 is installed\n");
    log("  2. Verify 12V VM wire is NOT bridged to AIN1 or BIN1\n");
    log("  3. Robot should be on blocks — wheels will spin\n\n");
    log("Expected directions (looking at robot from above):\n");
    log("  Left  forward = CCW rotation (BIN2=HIGH)\n");
    log("  Right forward = CW  rotation (AIN2=HIGH)\n");
    log("  If reversed: swap motor output wires at TB6612 terminal\n\n");
    log("Send 'g' to run test sequence\n");
    log("f=both fwd  b=both rev  l=left fwd  r=right fwd  s=stop\n");
}

void loop() {
    ArduinoOTA.handle();

    int c = read_char();
    if (c < 0) return;
    switch ((char)c) {
        case 'g': run_sequence(); break;
        case 'f': motor_set(PWMB_CH, BIN1, BIN2,  150); motor_set(PWMA_CH, AIN1, AIN2,  150); log("Both forward\n");      break;
        case 'b': motor_set(PWMB_CH, BIN1, BIN2, -150); motor_set(PWMA_CH, AIN1, AIN2, -150); log("Both reverse\n");      break;
        case 'l': motor_set(PWMB_CH, BIN1, BIN2,  150); motor_set(PWMA_CH, AIN1, AIN2,    0); log("Left forward only\n"); break;
        case 'r': motor_set(PWMB_CH, BIN1, BIN2,    0); motor_set(PWMA_CH, AIN1, AIN2,  150); log("Right forward only\n"); break;
        case 's': stop_all(); log("Stopped\n"); break;
    }
}
