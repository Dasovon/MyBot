#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoOTA.h>
#include <TelnetStream.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BNO055.h>
#include <Adafruit_INA219.h>
#include <micro_ros_platformio.h>
#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <geometry_msgs/msg/twist.h>
#include <nav_msgs/msg/odometry.h>
#include <sensor_msgs/msg/imu.h>
#include <sensor_msgs/msg/battery_state.h>
#include "credentials.h"

// ── Pins — Lonely Binary ESP32-S3 Expansion Base ──────────────────────
// TB6612: Motor A = RIGHT, Motor B = LEFT
#define PWMA     10
#define AIN1     11
#define AIN2     12
#define PWMB     13
#define BIN1     14
#define BIN2     15
#define PWMA_CH   0
#define PWMB_CH   1

// Encoders — ISR direction from validated Arduino firmware (fix #7):
//   left: A==B on CHANGE → forward  |  right: A!=B on CHANGE → forward
#define ENC_L_A  40
#define ENC_L_B  41
#define ENC_R_A  42
#define ENC_R_B  39

#define I2C_SDA   8
#define I2C_SCL   9

// ── Robot constants ───────────────────────────────────────────────────
static constexpr float WHEEL_RADIUS  = 0.034f;
static constexpr float WHEEL_SEP     = 0.179f;
static constexpr int   ENC_CPR       = 1010;
static constexpr float COUNTS_TO_RAD = (2.0f * M_PI) / ENC_CPR;

// ── PID — gains in rad/s error units ─────────────────────────────────
// Kd=0: derivative still reacts badly to EMA lag on step-like inputs — removed.
// Ki=5 + preseed: preseed sets integral so first tick delivers START_PWM_SEED PWM,
//   overcoming motor deadband instantly without the overshoot that Kd caused.
// Ki then handles steady-state tracking error.
static constexpr float KP            =  28.0f;
static constexpr float KD            =   0.0f;
static constexpr float KI            =   9.0f;
static constexpr float KI_MAX        =  12.0f;
static constexpr float START_PWM_SEED =  60.0f;  // PWM at first tick from standstill
static constexpr float RUN_PWM_FLOOR  =  55.0f;    // keep any active command above the deadband while target is nonzero
static constexpr float RUN_PWM_FLOOR_ACTUAL = 2.0f; // rad/s: only apply the floor while the wheel is still in the low-speed band
static constexpr uint32_t RUN_PWM_START_HOLD_MS = 400; // sustain the floor through the first part of a fresh move


// ── Velocity lowpass filter ───────────────────────────────────────────
// EMA velocity filter: suppresses left encoder EMI noise (GPIO40/41) before PID sees it.
// alpha=0.2 confirmed smooth turning/straight; fix hardware (100nF caps) to remove root cause.
static constexpr float VEL_ALPHA = 0.2f;
static float vel_l_filt = 0.0f, vel_r_filt = 0.0f;

static constexpr float REVERSAL_COAST_VEL = 3.0f;  // rad/s: coast before reversing a rolling wheel (raised from 0.8 — EMI noise on left encoder was false-triggering)
static float cmd_lin = 0.0f, cmd_ang = 0.0f;
// 3s is intentional: Pi WiFi + DDS jitter can cause brief gaps; tighter values cause false disarms during Nav2 autonomous runs.
static constexpr uint32_t CMD_TIMEOUT_MS = 3000;
static constexpr uint32_t CMD_FRESH_FOR_PING_MS = 750;
static constexpr uint32_t ARM_ZERO_HOLD_MS = 1000;
static uint32_t t_cmd_last  = 0;
static bool motion_armed = false;
static uint32_t zero_hold_start = 0;
static uint32_t nonzero_motion_start = 0;

struct PID { float target = 0.0f, prev_err = 0.0f, integral = 0.0f; };
static PID pid_l, pid_r;

static int pid_compute(PID& p, float actual, float dt) {
    if (fabsf(p.target) < 0.01f) {
        p.integral = 0.0f;
        p.prev_err = 0.0f;
        return 0;  // coast to stop
    }
    if ((p.target > 0.0f && actual < -REVERSAL_COAST_VEL) ||
        (p.target < 0.0f && actual >  REVERSAL_COAST_VEL)) {
        p.prev_err = p.target - actual;
        return 0;  // let momentum bleed off before applying reverse
    }
    float err = p.target - actual;
    p.integral = constrain(p.integral + err * dt, -KI_MAX, KI_MAX);
    float out = KP * err + KD * (err - p.prev_err) / dt + KI * p.integral;
    p.prev_err = err;
    bool in_start_hold = nonzero_motion_start > 0 &&
        (millis() - nonzero_motion_start) < RUN_PWM_START_HOLD_MS;
    if (fabsf(p.target) >= 0.01f &&
        (in_start_hold || fabsf(actual) < RUN_PWM_FLOOR_ACTUAL) &&
        fabsf(out) < RUN_PWM_FLOOR) {
        out = copysignf(RUN_PWM_FLOOR, p.target);
    }
    out = constrain(out, -255.0f, 255.0f);
    return (int)out;
}

// ── Encoders ──────────────────────────────────────────────────────────
static volatile long enc_l = 0, enc_r = 0;

void IRAM_ATTR isr_l() { enc_l += (digitalRead(ENC_L_A) == digitalRead(ENC_L_B)) ? 1 : -1; }
void IRAM_ATTR isr_r() { enc_r += (digitalRead(ENC_R_A) != digitalRead(ENC_R_B)) ? 1 : -1; }

// ── Motors ────────────────────────────────────────────────────────────
static void motor_set(uint8_t ch, uint8_t in1, uint8_t in2, int spd) {
    if      (spd > 0) { digitalWrite(in1, HIGH); digitalWrite(in2, LOW);  }
    else if (spd < 0) { digitalWrite(in1, LOW);  digitalWrite(in2, HIGH); spd = -spd; }
    else              { digitalWrite(in1, LOW);  digitalWrite(in2, LOW);  }
    ledcWrite(ch, (uint32_t)spd);
}

static void motors_stop() {
    motor_set(PWMB_CH, BIN1, BIN2, 0);
    motor_set(PWMA_CH, AIN1, AIN2, 0);
}

// ── Sensors ───────────────────────────────────────────────────────────
static Adafruit_BNO055 bno(55, 0x28, &Wire);
static Adafruit_INA219  ina(0x40);

// ── micro-ROS ─────────────────────────────────────────────────────────
enum State { WAITING, CONNECTED };
static State state = WAITING;
static unsigned long waiting_start = 0;

static rcl_publisher_t    pub_odom, pub_imu, pub_bat;
static rcl_subscription_t sub_cmd;
static nav_msgs__msg__Odometry        odom_msg;
static sensor_msgs__msg__Imu          imu_msg;
static sensor_msgs__msg__BatteryState bat_msg;
static geometry_msgs__msg__Twist      cmd_msg;
static rclc_executor_t executor;
static rcl_allocator_t allocator;
static rclc_support_t  support;
static rcl_node_t      node;

static char frame_odom[] = "odom";
static char frame_base[] = "base_footprint";
static char frame_imu[]  = "imu_link";
static char frame_bat[]  = "base_link";

// ── Odometry state ────────────────────────────────────────────────────
static float odom_x = 0.0f, odom_y = 0.0f, odom_th = 0.0f;
static long  prev_l = 0, prev_r = 0;

// ── Logging — TelnetStream only; Serial is owned by micro-ROS ─────────
template<typename... Args>
static void log(const char* fmt, Args... args) {
    char buf[256];
    snprintf(buf, sizeof(buf), fmt, args...);
    TelnetStream.print(buf);
}

static int read_telnet_char() {
    if (TelnetStream.available()) return TelnetStream.read();
    return -1;
}

// Resets encoder counts, odometry, and PID state only.
// Does NOT touch motion_armed, t_cmd_last, or zero_hold_start — safe to call
// mid-run without breaking the arming state.
static void reset_encoder_state() {
    noInterrupts();
    enc_l = 0;
    enc_r = 0;
    interrupts();
    prev_l = 0;
    prev_r = 0;
    odom_x = 0.0f;
    odom_y = 0.0f;
    odom_th = 0.0f;
    pid_l.prev_err = 0.0f;
    pid_r.prev_err = 0.0f;
    pid_l.integral = 0.0f;
    pid_r.integral = 0.0f;
    pid_l.target = 0.0f;
    pid_r.target = 0.0f;
    vel_l_filt = 0.0f;
    vel_r_filt = 0.0f;
}

// Full reset — used on agent reconnect. Also disarms motion and clears cmd state.
static void reset_motion_state() {
    reset_encoder_state();
    cmd_lin = 0.0f;
    cmd_ang = 0.0f;
    t_cmd_last = 0;
    motion_armed = false;
    zero_hold_start = 0;
    nonzero_motion_start = 0;
    motors_stop();
}

// ── cmd_vel callback ──────────────────────────────────────────────────
static void cmd_cb(const void* msg) {
    const auto* m = (const geometry_msgs__msg__Twist*)msg;
    cmd_lin = m->linear.x;
    cmd_ang = m->angular.z;
    t_cmd_last = millis();
    log("[cmd] lin=%.3f ang=%.3f armed=%d\n", cmd_lin, cmd_ang, motion_armed ? 1 : 0);
}

// ── micro-ROS entity management ───────────────────────────────────────
static bool create_entities() {
    allocator = rcl_get_default_allocator();
    if (rclc_support_init(&support, 0, NULL, &allocator)          != RCL_RET_OK) return false;
    if (rclc_node_init_default(&node, "esp32_robot", "", &support) != RCL_RET_OK) return false;

    if (rclc_publisher_init_default(&pub_odom, &node,
            ROSIDL_GET_MSG_TYPE_SUPPORT(nav_msgs, msg, Odometry),
            "/diff_cont/odom") != RCL_RET_OK) return false;

    if (rclc_publisher_init_default(&pub_imu, &node,
            ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, Imu),
            "/imu/imu") != RCL_RET_OK) return false;

    if (rclc_publisher_init_default(&pub_bat, &node,
            ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, BatteryState),
            "/battery_state") != RCL_RET_OK) return false;

    if (rclc_subscription_init_best_effort(&sub_cmd, &node,
            ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Twist),
            "/diff_cont/cmd_vel_unstamped") != RCL_RET_OK) return false;

    if (rclc_executor_init(&executor, &support.context, 1, &allocator) != RCL_RET_OK) return false;
    if (rclc_executor_add_subscription(&executor, &sub_cmd, &cmd_msg,
            &cmd_cb, ON_NEW_DATA) != RCL_RET_OK) return false;

    odom_msg.header.frame_id = {frame_odom, strlen(frame_odom), sizeof(frame_odom)};
    odom_msg.child_frame_id  = {frame_base, strlen(frame_base), sizeof(frame_base)};
    imu_msg.header.frame_id  = {frame_imu,  strlen(frame_imu),  sizeof(frame_imu)};
    bat_msg.header.frame_id  = {frame_bat,  strlen(frame_bat),  sizeof(frame_bat)};

    imu_msg.orientation_covariance[0]         = -1.0;  // EKF ignores orientation
    imu_msg.angular_velocity_covariance[0]    = 0.001;
    imu_msg.angular_velocity_covariance[4]    = 0.001;
    imu_msg.angular_velocity_covariance[8]    = 0.001;
    imu_msg.linear_acceleration_covariance[0] = 0.01;
    imu_msg.linear_acceleration_covariance[4] = 0.01;
    imu_msg.linear_acceleration_covariance[8] = 0.01;

    bat_msg.present              = true;
    bat_msg.power_supply_status  = 2;  // POWER_SUPPLY_STATUS_DISCHARGING

    return true;
}

static void destroy_entities() {
    rmw_context_t* rmw_ctx = rcl_context_get_rmw_context(&support.context);
    (void)rmw_uros_set_context_entity_destroy_session_timeout(rmw_ctx, 0);
    rcl_publisher_fini(&pub_odom, &node);
    rcl_publisher_fini(&pub_imu,  &node);
    rcl_publisher_fini(&pub_bat,  &node);
    rcl_subscription_fini(&sub_cmd, &node);
    rclc_executor_fini(&executor);
    rcl_node_fini(&node);
    rclc_support_fini(&support);
}

// ── WiFi / OTA ────────────────────────────────────────────────────────
static void wifi_setup() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) { delay(500); }
}

static void ota_setup() {
    ArduinoOTA.setHostname("esp32-mybot");
    ArduinoOTA.setPassword(OTA_PASSWORD);
    ArduinoOTA.onStart([]()                                    { log("[OTA] Starting...\n"); });
    ArduinoOTA.onEnd([]()                                      { log("[OTA] Done.\n"); });
    ArduinoOTA.onProgress([](unsigned int p, unsigned int t)   { log("[OTA] %u%%\r", p*100/t); });
    ArduinoOTA.onError([](ota_error_t e)                       { log("[OTA] Error[%u]\n", e); });
    ArduinoOTA.begin();
}

// ── Setup ─────────────────────────────────────────────────────────────
void setup() {
    pinMode(AIN1, OUTPUT); pinMode(AIN2, OUTPUT);
    pinMode(BIN1, OUTPUT); pinMode(BIN2, OUTPUT);
    ledcSetup(PWMA_CH, 1000, 8); ledcAttachPin(PWMA, PWMA_CH);
    ledcSetup(PWMB_CH, 1000, 8); ledcAttachPin(PWMB, PWMB_CH);
    motors_stop();

    pinMode(ENC_L_A, INPUT_PULLUP); pinMode(ENC_L_B, INPUT_PULLUP);
    pinMode(ENC_R_A, INPUT_PULLUP); pinMode(ENC_R_B, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(ENC_L_A), isr_l, CHANGE);
    attachInterrupt(digitalPinToInterrupt(ENC_R_A), isr_r, CHANGE);

    Wire.begin(I2C_SDA, I2C_SCL);
    bno.begin();
    bno.setExtCrystalUse(true);
    ina.begin();

    Serial.begin(115200);
    delay(500);
    wifi_setup();
    ota_setup();
    TelnetStream.begin();

    // Serial handed to micro-ROS transport after this point — use TelnetStream for logging
    set_microros_serial_transports(Serial);

    log("[esp32_robot] ready — agent: ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0\n");
}

// ── Loop timers ───────────────────────────────────────────────────────
static uint32_t t_control = 0;
static uint8_t  log_tick  = 0;   // log every control tick for count-threshold tests
static uint32_t t_battery = 0;
static uint32_t t_ping    = 0;

void loop() {
    ArduinoOTA.handle();
    uint32_t now = millis();

    int c = read_telnet_char();
    if (c == 'r') {
        reset_encoder_state();
        log("[esp32_robot] enc reset\n");
    }

    switch (state) {
        case WAITING:
            if (waiting_start == 0) waiting_start = millis();
            if (rmw_uros_ping_agent(500, 3) == RMW_RET_OK) {
                waiting_start = 0;
                if (create_entities()) {
                    rmw_uros_sync_session(1000);
                    reset_motion_state();
                    t_control = now; t_battery = now; t_ping = now;
                    state = CONNECTED;
                    log("[esp32_robot] connected\n");
                }
            } else if (millis() - waiting_start > 30000) {
                log("[esp32_robot] no agent for 30s — restarting\n");
                esp_restart();
            }
            break;

        case CONNECTED:
            rclc_executor_spin_some(&executor, RCL_MS_TO_NS(10));
            now = millis();  // refresh: cmd_cb sets t_cmd_last inside spin; stale now would underflow CMD_TIMEOUT

            // Control + odom + IMU @ 30 Hz
            if (now - t_control >= 33) {
                float dt = (now - t_control) * 0.001f;
                t_control = now;

                noInterrupts();
                long l = enc_l, r = enc_r;
                interrupts();

                long  dl    = l - prev_l;
                long  dr    = r - prev_r;
                prev_l = l; prev_r = r;

                float vel_l = (float)dl * COUNTS_TO_RAD / dt;  // rad/s
                float vel_r = (float)dr * COUNTS_TO_RAD / dt;

                vel_l_filt = VEL_ALPHA * vel_l + (1.0f - VEL_ALPHA) * vel_l_filt;
                vel_r_filt = VEL_ALPHA * vel_r + (1.0f - VEL_ALPHA) * vel_r_filt;

                // Command timeout: zero cmd if no message received within CMD_TIMEOUT_MS
                if (t_cmd_last > 0 && (now - t_cmd_last) > CMD_TIMEOUT_MS) {
                    cmd_lin = 0.0f;
                    cmd_ang = 0.0f;
                    motion_armed = false;
                }

                bool cmd_is_zero = fabsf(cmd_lin) < 0.01f && fabsf(cmd_ang) < 0.01f;
                if (!motion_armed) {
                    if (cmd_is_zero) {
                        if (zero_hold_start == 0) {
                            zero_hold_start = now;
                        } else if (now - zero_hold_start >= ARM_ZERO_HOLD_MS) {
                            motion_armed = true;
                            log("[esp32_robot] motion armed after zero hold\n");
                        }
                    } else {
                        zero_hold_start = 0;
                    }
                    nonzero_motion_start = 0;
                } else if (cmd_is_zero) {
                    zero_hold_start = 0;
                    nonzero_motion_start = 0;
                } else {
                    zero_hold_start = 0;
                    if (nonzero_motion_start == 0) {
                        nonzero_motion_start = now;
                        log("[esp32_robot] motion command active\n");
                    }
                }

                if (!motion_armed) {
                    pid_l.target = 0.0f;
                    pid_r.target = 0.0f;
                    pid_l.prev_err = 0.0f;
                    pid_r.prev_err = 0.0f;
                    pid_l.integral = 0.0f;
                    pid_r.integral = 0.0f;
                    motors_stop();
                    if (++log_tick >= 1) {
                        log_tick = 0;
                        log("[enc] cnt=%ld/%ld tgt=0.00/0.00 act=%.2f/%.2f filt=%.2f/%.2f\n",
                            l, r, vel_l, vel_r, vel_l_filt, vel_r_filt);
                    }
                } else {
                    // Commands arrive directly from twist_mux on the Pi; the ESP32 applies its own
                    // start preseed, timeout, and reversal-coast handling here.
                    float tl = (cmd_lin - cmd_ang * WHEEL_SEP * 0.5f) / WHEEL_RADIUS;
                    float tr = (cmd_lin + cmd_ang * WHEEL_SEP * 0.5f) / WHEEL_RADIUS;

                    // Preseed integral on rest→move transition so first tick delivers
                    // START_PWM_SEED PWM — overcomes motor deadband without Kd overshoot.
                    auto preseed = [&](PID& p, float nt) {
                        if (fabsf(p.target) < 0.01f && fabsf(nt) > 0.01f) {
                            float s = (nt > 0.0f) ? 1.0f : -1.0f;
                            p.integral = constrain(
                                s * (START_PWM_SEED - KP * fabsf(nt)) / KI,
                                -KI_MAX, KI_MAX);
                        }
                    };
                    preseed(pid_l, tl);
                    preseed(pid_r, tr);

                    pid_l.target = tl;
                    pid_r.target = tr;

                    int pwm_l = pid_compute(pid_l, vel_l_filt, dt);
                    int pwm_r = pid_compute(pid_r, vel_r_filt, dt);
                    motor_set(PWMB_CH, BIN1, BIN2, pwm_l);
                    motor_set(PWMA_CH, AIN1, AIN2, pwm_r);
                    if (++log_tick >= 1) {
                        log_tick = 0;
                        log("[enc] cnt=%ld/%ld tgt=%.2f/%.2f act=%.2f/%.2f filt=%.2f/%.2f\n",
                            l, r, pid_l.target, pid_r.target, vel_l, vel_r, vel_l_filt, vel_r_filt);
                    }
                }

                float dist_l = (float)dl * COUNTS_TO_RAD * WHEEL_RADIUS;
                float dist_r = (float)dr * COUNTS_TO_RAD * WHEEL_RADIUS;
                float dist   = (dist_l + dist_r) * 0.5f;
                float dth    = (dist_r - dist_l) / WHEEL_SEP;
                odom_x  += dist * cosf(odom_th + dth * 0.5f);
                odom_y  += dist * sinf(odom_th + dth * 0.5f);
                odom_th += dth;

                int64_t  ts  = rmw_uros_epoch_nanos();
                int32_t  sec = (int32_t)(ts / 1000000000LL);
                uint32_t ns  = (uint32_t)(ts % 1000000000LL);

                odom_msg.header.stamp.sec          = sec;
                odom_msg.header.stamp.nanosec      = ns;
                odom_msg.pose.pose.position.x      = odom_x;
                odom_msg.pose.pose.position.y      = odom_y;
                odom_msg.pose.pose.orientation.z   = sinf(odom_th * 0.5f);
                odom_msg.pose.pose.orientation.w   = cosf(odom_th * 0.5f);
                odom_msg.twist.twist.linear.x      = (vel_l + vel_r) * 0.5f * WHEEL_RADIUS;
                odom_msg.twist.twist.angular.z     = (vel_r - vel_l) * WHEEL_RADIUS / WHEEL_SEP;
                rcl_publish(&pub_odom, &odom_msg, NULL);

                imu::Quaternion q  = bno.getQuat();
                imu::Vector<3>  av = bno.getVector(Adafruit_BNO055::VECTOR_GYROSCOPE);
                imu::Vector<3>  la = bno.getVector(Adafruit_BNO055::VECTOR_LINEARACCEL);
                imu_msg.header.stamp.sec          = sec;
                imu_msg.header.stamp.nanosec      = ns;
                imu_msg.orientation.x             = q.x();
                imu_msg.orientation.y             = q.y();
                imu_msg.orientation.z             = q.z();
                imu_msg.orientation.w             = q.w();
                // BNO055 VECTOR_GYROSCOPE returns dps; Imu message expects rad/s
                static constexpr float DEG2RAD = M_PI / 180.0f;
                imu_msg.angular_velocity.x        = av.x() * DEG2RAD;
                imu_msg.angular_velocity.y        = av.y() * DEG2RAD;
                imu_msg.angular_velocity.z        = av.z() * DEG2RAD;
                imu_msg.linear_acceleration.x     = la.x();
                imu_msg.linear_acceleration.y     = la.y();
                imu_msg.linear_acceleration.z     = la.z();
                rcl_publish(&pub_imu, &imu_msg, NULL);
            }

            // Ping only when the command stream is stale. vel_smoother publishes
            // at 50 Hz, so fresh cmd_vel traffic is a better health signal than
            // rmw_uros_ping_agent(), which can false-fail while data is flowing.
            uint32_t cmd_age = (t_cmd_last > 0) ? (now - t_cmd_last) : UINT32_MAX;
            if (cmd_age > CMD_FRESH_FOR_PING_MS && now - t_ping >= 2000) {
                t_ping = now;
                if (rmw_uros_ping_agent(500, 1) != RMW_RET_OK) {
                    reset_motion_state();
                    destroy_entities();
                    state = WAITING;
                    waiting_start = 0;
                    log("[esp32_robot] agent lost — reconnecting...\n");
                }
            }
            break;
    }

    // Battery @ 1 Hz is always available over Telnet, even when the ROS bridge is down.
    if (now - t_battery >= 1000) {
        t_battery = now;
        float v   = ina.getBusVoltage_V();
        float i_A = ina.getCurrent_mA() * 0.001f;
        bat_msg.voltage = v;
        bat_msg.current = i_A;
        if (state == CONNECTED) {
            rcl_publish(&pub_bat, &bat_msg, NULL);
        }
        log("[bat] %.2fV  %.3fA\n", v, i_A);
    }
}
