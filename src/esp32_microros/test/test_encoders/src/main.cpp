#include <Arduino.h>

// Encoder pins — ESP32-S3-DevKitC-1 (GPIO34-39 don't exist on S3)
#define ENC_L_A  40
#define ENC_L_B  41
#define ENC_R_A  42
#define ENC_R_B  43

// ISR direction matches validated Arduino firmware (fix #7):
//   left:  A == B on CHANGE → forward (+)
//   right: A != B on CHANGE → forward (+)
// If a wheel counts backwards, swap == / != for that encoder.

static volatile long enc_l = 0, enc_r = 0;

void IRAM_ATTR isr_l() { enc_l += (digitalRead(ENC_L_A) == digitalRead(ENC_L_B)) ? 1 : -1; }
void IRAM_ATTR isr_r() { enc_r += (digitalRead(ENC_R_A) != digitalRead(ENC_R_B)) ? 1 : -1; }

static constexpr int   ENC_CPR      = 1010;
static constexpr float COUNTS_TO_M  = (2.0f * M_PI * 0.034f) / ENC_CPR;  // counts → metres

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== Encoder Test ===");
    Serial.println("Pins: L_A=GPIO40  L_B=GPIO41  R_A=GPIO42  R_B=GPIO43");
    Serial.println("Spin wheels FORWARD by hand — counts should go positive.");
    Serial.println("Send 'r' to reset counters.");
    Serial.println();
    Serial.println("       Left counts   Left m/s    Right counts  Right m/s");
}

static long  prev_l = 0, prev_r = 0;
static uint32_t t_last = 0;

void loop() {
    if (Serial.available() && Serial.read() == 'r') {
        noInterrupts(); enc_l = 0; enc_r = 0; interrupts();
        prev_l = 0; prev_r = 0;
        Serial.println("--- reset ---");
    }

    uint32_t now = millis();
    if (now - t_last < 250) return;
    float dt = (now - t_last) * 0.001f;
    t_last = now;

    noInterrupts();
    long l = enc_l;
    long r = enc_r;
    interrupts();

    float vel_l = (l - prev_l) * COUNTS_TO_M / dt;
    float vel_r = (r - prev_r) * COUNTS_TO_M / dt;
    prev_l = l;
    prev_r = r;

    // Flag direction mismatch — both wheels should go positive together
    const char* warn = (l != 0 && r != 0 && ((l > 0) != (r > 0))) ? " [!! DIRECTION MISMATCH]" : "";

    Serial.printf("  L: %7ld  (%+5.3f m/s)    R: %7ld  (%+5.3f m/s)%s\n",
        l, vel_l, r, vel_r, warn);
}
