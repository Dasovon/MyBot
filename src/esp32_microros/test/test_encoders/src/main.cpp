#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoOTA.h>
#include <TelnetStream.h>
#include "credentials.h"

// Encoder pins — Lonely Binary ESP32-S3 Expansion Base
#define ENC_L_A  40
#define ENC_L_B  41
#define ENC_R_A  42
#define ENC_R_B  39

// ISR direction matches validated Arduino firmware (fix #7):
//   left:  A == B on CHANGE → forward (+)
//   right: A != B on CHANGE → forward (+)
// If a wheel counts backwards, swap == / != for that encoder.

static volatile long enc_l = 0, enc_r = 0;

void IRAM_ATTR isr_l() { enc_l += (digitalRead(ENC_L_A) == digitalRead(ENC_L_B)) ? 1 : -1; }
void IRAM_ATTR isr_r() { enc_r += (digitalRead(ENC_R_A) != digitalRead(ENC_R_B)) ? 1 : -1; }

static constexpr int   ENC_CPR     = 1010;
static constexpr float COUNTS_TO_M = (2.0f * M_PI * 0.034f) / ENC_CPR;

template<typename... Args>
static void log(const char* fmt, Args... args) {
    char buf[256];
    snprintf(buf, sizeof(buf), fmt, args...);
    Serial.print(buf);
    TelnetStream.print(buf);
}

static int read_char() {
    if (Serial.available())      return Serial.read();
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

void setup() {
    Serial.begin(115200);
    delay(500);

    wifi_setup();
    ota_setup();
    TelnetStream.begin();
    Serial.println("[Telnet] port 23 — connect: nc 192.168.86.43 23");

    pinMode(ENC_L_A, INPUT_PULLUP);
    pinMode(ENC_L_B, INPUT_PULLUP);
    pinMode(ENC_R_A, INPUT_PULLUP);
    pinMode(ENC_R_B, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(ENC_L_A), isr_l, CHANGE);
    attachInterrupt(digitalPinToInterrupt(ENC_R_A), isr_r, CHANGE);

    log("\n=== Encoder Test ===\n");
    log("Pins: L_A=GPIO40  L_B=GPIO41  R_A=GPIO42  R_B=GPIO39\n");
    log("Spin wheels FORWARD by hand — counts should go positive.\n");
    log("Send 'r' to reset counters.\n\n");
    log("       Left counts   Left m/s    Right counts  Right m/s\n");
}

static long     prev_l = 0, prev_r = 0;
static uint32_t t_last = 0;

void loop() {
    ArduinoOTA.handle();

    int c = read_char();
    if (c == 'r') {
        noInterrupts(); enc_l = 0; enc_r = 0; interrupts();
        prev_l = 0; prev_r = 0;
        log("--- reset ---\n");
    }

    uint32_t now = millis();
    if (now - t_last < 250) return;
    float dt = (now - t_last) * 0.001f;
    t_last = now;

    noInterrupts();
    long l = enc_l, r = enc_r;
    interrupts();

    float vel_l = (l - prev_l) * COUNTS_TO_M / dt;
    float vel_r = (r - prev_r) * COUNTS_TO_M / dt;
    prev_l = l;
    prev_r = r;

    const char* warn = (l != 0 && r != 0 && ((l > 0) != (r > 0))) ? " [!! DIRECTION MISMATCH]" : "";
    log("  L: %7ld  (%+5.3f m/s)    R: %7ld  (%+5.3f m/s)%s\n", l, vel_l, r, vel_r, warn);
}
