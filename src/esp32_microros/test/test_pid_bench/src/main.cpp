#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoOTA.h>
#include <TelnetStream.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_INA219.h>
#include "credentials.h"

// TB6612 pins — Lonely Binary ESP32-S3 Expansion Base
#define PWMA     10
#define AIN1     11
#define AIN2     12
#define PWMB     13
#define BIN1     14
#define BIN2     15
#define PWMA_CH   0
#define PWMB_CH   1

// Encoders
#define ENC_L_A  40
#define ENC_L_B  41
#define ENC_R_A  42
#define ENC_R_B  39

// Robot constants
static constexpr float WHEEL_RADIUS  = 0.034f;
static constexpr float WHEEL_SEP     = 0.179f;
static constexpr int   ENC_CPR       = 1010;
static constexpr float COUNTS_TO_RAD = (2.0f * M_PI) / ENC_CPR;

// PID constants match the live drive firmware
static constexpr float KP            = 28.0f;
static constexpr float KD            = 0.0f;
static constexpr float KI            = 9.0f;
static constexpr float KI_MAX        = 24.0f;
static constexpr float START_PWM_SEED = 120.0f;
static constexpr float RUN_PWM_FLOOR  = 72.0f;
static constexpr float RUN_PWM_FLOOR_ACTUAL = 2.0f;
static constexpr uint32_t RUN_PWM_START_HOLD_MS = 400;
static constexpr float VEL_ALPHA      = 0.2f;
static constexpr float REVERSAL_COAST_VEL = 3.0f;
static constexpr uint32_t CONTROL_PERIOD_MS = 33;
static constexpr uint32_t BATTERY_PERIOD_MS = 1000;

// PID state
struct PID {
    float target = 0.0f;
    float prev_err = 0.0f;
    float integral = 0.0f;
};

static PID pid_l, pid_r;
static float vel_l_filt = 0.0f, vel_r_filt = 0.0f;
static volatile long enc_l = 0, enc_r = 0;
static long prev_l = 0, prev_r = 0;
static uint32_t t_control = 0;
static uint32_t t_battery = 0;
static uint32_t t_mode = 0;
static uint32_t motion_start_ms = 0;

static Adafruit_INA219 ina(0x40);

enum RunMode { MODE_IDLE, MODE_PID, MODE_POWER };
static RunMode run_mode = MODE_IDLE;

enum AutoStage { AUTO_WAIT, AUTO_PID, AUTO_POWER, AUTO_DONE };
static AutoStage auto_stage = AUTO_WAIT;
static uint32_t auto_start_at = 0;
static constexpr uint32_t AUTO_DELAY_MS = 3000;

enum PowerPhase { POWER_RAMP_UP, POWER_HOLD_UP, POWER_RAMP_DOWN, POWER_DONE };
static PowerPhase power_phase = POWER_DONE;

static constexpr float PID_LIN = 0.25f;
static constexpr float PID_ANG = 0.0f;
static constexpr long PID_GOAL_COUNTS = 1010;
static constexpr long PID_MAX_COUNTS = 3030;
static constexpr long PID_EXTEND_COUNTS = 1010;
static constexpr float PID_EXTEND_FLOOR = 0.50f;
static bool pid_adaptive = true;
static long pid_goal_counts = PID_GOAL_COUNTS;
static uint32_t pid_started_at = 0;
static uint32_t pid_phase_started_at = 0;
static const uint32_t pid_arm_ms = 600;
static const uint32_t pid_stop_ms = 500;
static const uint32_t pid_timeout_ms = 12000;

static int power_pwm = 0;
static uint32_t power_next_step_ms = 0;
static const int power_steps[] = {80, 110, 140, 170, 200, 170, 140, 110, 80, 0};
static constexpr size_t power_steps_len = sizeof(power_steps) / sizeof(power_steps[0]);
static size_t power_step_idx = 0;

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
    Serial.printf("\n[WiFi] Connected - IP: %s\n", WiFi.localIP().toString().c_str());
}

static void ota_setup() {
    ArduinoOTA.setHostname("esp32-mybot");
    ArduinoOTA.setPassword(OTA_PASSWORD);
    ArduinoOTA.onStart([]() { log("[OTA] Starting...\n"); });
    ArduinoOTA.onEnd([]()   { log("[OTA] Done.\n"); });
    ArduinoOTA.onProgress([](unsigned int p, unsigned int t) { log("[OTA] %u%%\r", p * 100 / t); });
    ArduinoOTA.onError([](ota_error_t e) { log("[OTA] Error[%u]\n", e); });
    ArduinoOTA.begin();
    Serial.println("[OTA] Ready - hostname: esp32-mybot");
}

static void motor_set(uint8_t ch, uint8_t in1, uint8_t in2, int spd) {
    if      (spd > 0) { digitalWrite(in1, HIGH); digitalWrite(in2, LOW);  }
    else if (spd < 0) { digitalWrite(in1, LOW);  digitalWrite(in2, HIGH); spd = -spd; }
    else              { digitalWrite(in1, LOW);  digitalWrite(in2, LOW);  }
    ledcWrite(ch, (uint32_t)constrain(spd, 0, 255));
}

static void motors_stop() {
    motor_set(PWMB_CH, BIN1, BIN2, 0);
    motor_set(PWMA_CH, AIN1, AIN2, 0);
}

void IRAM_ATTR isr_l() { enc_l += (digitalRead(ENC_L_A) == digitalRead(ENC_L_B)) ? 1 : -1; }
void IRAM_ATTR isr_r() { enc_r += (digitalRead(ENC_R_A) != digitalRead(ENC_R_B)) ? 1 : -1; }

static void reset_motion_state() {
    noInterrupts();
    enc_l = 0;
    enc_r = 0;
    interrupts();
    prev_l = 0;
    prev_r = 0;
    pid_l = PID{};
    pid_r = PID{};
    vel_l_filt = 0.0f;
    vel_r_filt = 0.0f;
    motors_stop();
    motion_start_ms = 0;
}

static int pid_compute(PID& p, float actual, float dt) {
    if (fabsf(p.target) < 0.01f) {
        p.integral = 0.0f;
        p.prev_err = 0.0f;
        return 0;
    }
    if ((p.target > 0.0f && actual < -REVERSAL_COAST_VEL) ||
        (p.target < 0.0f && actual >  REVERSAL_COAST_VEL)) {
        p.prev_err = p.target - actual;
        return 0;
    }
    float err = p.target - actual;
    p.integral = constrain(p.integral + err * dt, -KI_MAX, KI_MAX);
    float out = KP * err + KD * (err - p.prev_err) / dt + KI * p.integral;
    p.prev_err = err;
    bool in_start_hold = motion_start_ms > 0 &&
        (millis() - motion_start_ms) < RUN_PWM_START_HOLD_MS;
    if (fabsf(p.target) >= 0.01f &&
        (in_start_hold || fabsf(actual) < RUN_PWM_FLOOR_ACTUAL) &&
        fabsf(out) < RUN_PWM_FLOOR) {
        out = copysignf(RUN_PWM_FLOOR, p.target);
    }
    out = constrain(out, -255.0f, 255.0f);
    return (int)out;
}

static void start_pid_bench() {
    reset_motion_state();
    pid_goal_counts = PID_GOAL_COUNTS;
    pid_started_at = millis();
    pid_phase_started_at = millis();
    motion_start_ms = millis();
    run_mode = MODE_PID;
    t_mode = millis();
    log("\n[bench] pid start target=%.2f m/s goal=%ld counts\n", PID_LIN, pid_goal_counts);
}

static void start_power_sweep() {
    reset_motion_state();
    power_phase = POWER_RAMP_UP;
    power_step_idx = 0;
    power_next_step_ms = millis();
    power_pwm = power_steps[power_step_idx];
    run_mode = MODE_POWER;
    t_mode = millis();
    log("\n[bench] power sweep start\n");
}

static void stop_all() {
    run_mode = MODE_IDLE;
    power_phase = POWER_DONE;
    pid_l.target = 0.0f;
    pid_r.target = 0.0f;
    motors_stop();
    log("[bench] stop\n");
}

static void start_auto_sequence() {
    auto_stage = AUTO_PID;
    auto_start_at = millis();
    log("[bench] auto sequence armed\n");
}

static bool bench_motion_alive(float act_l, float act_r) {
    return min(fabsf(act_l), fabsf(act_r)) >= PID_EXTEND_FLOOR;
}

static void handle_cmd(int c) {
    if (c < 0) return;
    switch ((char)c) {
        case 'r':
            reset_motion_state();
            log("[bench] reset\n");
            break;
        case 't':
            start_pid_bench();
            break;
        case 'p':
            start_power_sweep();
            break;
        case 's':
            stop_all();
            break;
        case 'h':
            log("\nCommands:\n");
            log("  t = pid tuning run (adaptive 1 to 3 rev)\n");
            log("  p = power sweep\n");
            log("  r = reset encoders\n");
            log("  s = stop motors\n");
            break;
    }
}

void setup() {
    Serial.begin(115200);
    delay(500);

    wifi_setup();
    ota_setup();
    TelnetStream.begin();
    Serial.println("[Telnet] port 23 - connect: nc esp32-mybot.local 23");

    pinMode(AIN1, OUTPUT); pinMode(AIN2, OUTPUT);
    pinMode(BIN1, OUTPUT); pinMode(BIN2, OUTPUT);
    ledcSetup(PWMA_CH, 1000, 8); ledcAttachPin(PWMA, PWMA_CH);
    ledcSetup(PWMB_CH, 1000, 8); ledcAttachPin(PWMB, PWMB_CH);

    pinMode(ENC_L_A, INPUT_PULLUP);
    pinMode(ENC_L_B, INPUT_PULLUP);
    pinMode(ENC_R_A, INPUT_PULLUP);
    pinMode(ENC_R_B, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(ENC_L_A), isr_l, CHANGE);
    attachInterrupt(digitalPinToInterrupt(ENC_R_A), isr_r, CHANGE);

    Wire.begin(8, 9);
    ina.begin();

    stop_all();
    log("\n=== ESP32 PID Bench ===\n");
    log("Commands: h=help  t=pid bench  p=power sweep  r=reset  s=stop\n");
    log("Wheel radius=%.3f m  CPR=%d\n", WHEEL_RADIUS, ENC_CPR);
    start_auto_sequence();
}

static void log_sample(uint32_t now, const char* stage, long l, long r, float tl, float tr, float vel_l, float vel_r, float vel_l_filt, float vel_r_filt, int pwm_l, int pwm_r) {
    float v = ina.getBusVoltage_V();
    float i_A = ina.getCurrent_mA() * 0.001f;
    log("[bench] t=%lu stage=%s cnt=%ld/%ld tgt=%.2f/%.2f act=%.2f/%.2f filt=%.2f/%.2f pwm=%d/%d bat=%.2fV curr=%.3fA\n",
        (unsigned long)now, stage, l, r, tl, tr, vel_l, vel_r, vel_l_filt, vel_r_filt, pwm_l, pwm_r, v, i_A);
}

void loop() {
    ArduinoOTA.handle();

    int c = read_char();
    if (c >= 0) handle_cmd(c);

    if (run_mode == MODE_IDLE && auto_stage == AUTO_PID && (millis() - auto_start_at) >= AUTO_DELAY_MS) {
        start_pid_bench();
    }

    uint32_t now = millis();

    const char* bench_stage = "idle";

    if (run_mode == MODE_POWER) {
        if (now - power_next_step_ms >= 1200) {
            power_next_step_ms = now;
            if (power_step_idx + 1 < power_steps_len) {
                power_step_idx++;
                power_pwm = power_steps[power_step_idx];
                if (power_step_idx == power_steps_len - 1) {
                    power_phase = POWER_DONE;
                }
            }
        }
        motor_set(PWMB_CH, BIN1, BIN2, power_pwm);
        motor_set(PWMA_CH, AIN1, AIN2, power_pwm);
        bench_stage = "power";
    } else if (run_mode == MODE_IDLE) {
        motors_stop();
    }

    if (now - t_control < CONTROL_PERIOD_MS) return;
    float dt = (now - t_control) * 0.001f;
    t_control = now;

    noInterrupts();
    long l = enc_l;
    long r = enc_r;
    interrupts();

    long dl = l - prev_l;
    long dr = r - prev_r;
    prev_l = l;
    prev_r = r;

    float vel_l = (float)dl * COUNTS_TO_RAD / dt;
    float vel_r = (float)dr * COUNTS_TO_RAD / dt;
    vel_l_filt = VEL_ALPHA * vel_l + (1.0f - VEL_ALPHA) * vel_l_filt;
    vel_r_filt = VEL_ALPHA * vel_r + (1.0f - VEL_ALPHA) * vel_r_filt;

    float tl = 0.0f;
    float tr = 0.0f;
    int pwm_l = 0;
    int pwm_r = 0;

    if (run_mode == MODE_PID) {
        if (pid_phase_started_at == pid_started_at && (now - pid_started_at) < pid_arm_ms) {
            tl = 0.0f;
            tr = 0.0f;
            bench_stage = "arm";
        } else {
            tl = (PID_LIN - PID_ANG * WHEEL_SEP * 0.5f) / WHEEL_RADIUS;
            tr = (PID_LIN + PID_ANG * WHEEL_SEP * 0.5f) / WHEEL_RADIUS;
            pid_l.target = tl;
            pid_r.target = tr;
            bench_stage = "active";
            pwm_l = pid_compute(pid_l, vel_l_filt, dt);
            pwm_r = pid_compute(pid_r, vel_r_filt, dt);
            motor_set(PWMB_CH, BIN1, BIN2, pwm_l);
            motor_set(PWMA_CH, AIN1, AIN2, pwm_r);

            if (l >= pid_goal_counts || r >= pid_goal_counts) {
                if (pid_goal_counts < PID_MAX_COUNTS && bench_motion_alive(vel_l_filt, vel_r_filt)) {
                    pid_goal_counts = min(PID_MAX_COUNTS, pid_goal_counts + PID_EXTEND_COUNTS);
                    log("[bench] extend goal=%ld counts (%.2f rev)\n", pid_goal_counts, pid_goal_counts / (float)ENC_CPR);
                } else if ((now - pid_started_at) > pid_timeout_ms) {
                    log("[bench] pid timeout before goal\n");
                    if (auto_stage == AUTO_PID) {
                        auto_stage = AUTO_POWER;
                        start_power_sweep();
                    } else {
                        stop_all();
                    }
                } else {
                    log("[bench] pid complete goal=%ld counts\n", pid_goal_counts);
                    if (auto_stage == AUTO_PID) {
                        auto_stage = AUTO_POWER;
                        start_power_sweep();
                    } else {
                        stop_all();
                    }
                }
            }
        }
    } else if (run_mode == MODE_POWER) {
        pwm_l = power_pwm;
        pwm_r = power_pwm;
        tl = 0.0f;
        tr = 0.0f;
        if (power_phase == POWER_DONE) {
            motor_set(PWMB_CH, BIN1, BIN2, 0);
            motor_set(PWMA_CH, AIN1, AIN2, 0);
            log("[bench] power sweep complete\n");
            auto_stage = AUTO_DONE;
            run_mode = MODE_IDLE;
        }
    }

    if (run_mode != MODE_IDLE) {
        log_sample(now - t_mode, bench_stage, l, r, tl, tr, vel_l, vel_r, vel_l_filt, vel_r_filt, pwm_l, pwm_r);
    }

    if (now - t_battery >= BATTERY_PERIOD_MS) {
        t_battery = now;
        float v = ina.getBusVoltage_V();
        float i_A = ina.getCurrent_mA() * 0.001f;
        log("[bat] %.2fV %.3fA\n", v, i_A);
    }
}
