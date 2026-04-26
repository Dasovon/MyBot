#include <Arduino.h>
#include <micro_ros_arduino.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BNO055.h>

#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <geometry_msgs/msg/twist.h>
#include <nav_msgs/msg/odometry.h>
#include <sensor_msgs/msg/imu.h>

// ── Pin definitions ───────────────────────────────────────────────
// TB6612 — Motor A = RIGHT, Motor B = LEFT (matches firmware convention)
#define PWMA  25    // right motor speed
#define AIN2  26    // right motor dir B
#define AIN1  27    // right motor dir A
#define PWMB  14    // left motor speed
#define BIN1  32    // left motor dir A
#define BIN2  33    // left motor dir B

// Encoders on input-only pins (no pullup needed — encoder outputs are push-pull)
// Direction logic matches validated Arduino firmware (fix #7):
//   left:  A == B on change → forward (+)
//   right: A != B on change → forward (+)
#define ENC_L_A  36
#define ENC_L_B  39
#define ENC_R_A  34
#define ENC_R_B  35

// BNO055 I2C — hardware default pins
#define I2C_SDA  21
#define I2C_SCL  22

// ── Robot constants ───────────────────────────────────────────────
static constexpr float WHEEL_RADIUS  = 0.034f;
static constexpr float WHEEL_SEP     = 0.179f;
static constexpr int   ENC_CPR       = 1010;
static constexpr float COUNTS_TO_RAD = (2.0f * M_PI) / ENC_CPR;

// ── PID ───────────────────────────────────────────────────────────
// Starting values from validated Arduino firmware — expect re-tuning after first spin test
// Units: target/actual in rad/s, output in PWM [-255, 255]
static constexpr float KP = 20.0f;
static constexpr float KD = 12.0f;
// Ki = 0 per validated config

struct PID { float target = 0, prev_err = 0; };
static PID pid_l, pid_r;

static int pid_compute(PID& p, float actual, float dt) {
    float err = p.target - actual;
    float out = KP * err + KD * (err - p.prev_err) / dt;
    p.prev_err = err;
    return constrain((int)out, -255, 255);
}

// ── Encoders ─────────────────────────────────────────────────────
static volatile long enc_l = 0, enc_r = 0;

void IRAM_ATTR isr_enc_l() {
    enc_l += (digitalRead(ENC_L_A) == digitalRead(ENC_L_B)) ? 1 : -1;
}
void IRAM_ATTR isr_enc_r() {
    enc_r += (digitalRead(ENC_R_A) != digitalRead(ENC_R_B)) ? 1 : -1;
}

// ── Motor control ─────────────────────────────────────────────────
static void motor_set(uint8_t pwm_pin, uint8_t in1, uint8_t in2, int spd) {
    if      (spd > 0) { digitalWrite(in1, HIGH); digitalWrite(in2, LOW);  }
    else if (spd < 0) { digitalWrite(in1, LOW);  digitalWrite(in2, HIGH); spd = -spd; }
    else              { digitalWrite(in1, LOW);  digitalWrite(in2, LOW);  }
    ledcWrite(pwm_pin, (uint32_t)spd);
}

// ── micro-ROS ─────────────────────────────────────────────────────
static rcl_publisher_t    pub_odom, pub_imu;
static rcl_subscription_t sub_cmd;
static nav_msgs__msg__Odometry   odom_msg;
static sensor_msgs__msg__Imu     imu_msg;
static geometry_msgs__msg__Twist cmd_msg;

static rclc_executor_t executor;
static rcl_allocator_t allocator;
static rclc_support_t  support;
static rcl_node_t      node;

#define RCCHECK(fn) { if ((fn) != RCL_RET_OK) { for (;;) {} } }

static void cmd_cb(const void* msg) {
    const auto* m = (const geometry_msgs__msg__Twist*)msg;
    float lin = m->linear.x;
    float ang = m->angular.z;
    // Convert body velocity to wheel angular velocity (rad/s)
    pid_l.target = (lin - ang * WHEEL_SEP * 0.5f) / WHEEL_RADIUS;
    pid_r.target = (lin + ang * WHEEL_SEP * 0.5f) / WHEEL_RADIUS;
}

// ── BNO055 ────────────────────────────────────────────────────────
static Adafruit_BNO055 bno(55, 0x28, &Wire);

// ── Odometry state ────────────────────────────────────────────────
static float odom_x = 0, odom_y = 0, odom_th = 0;
static long  prev_l = 0, prev_r = 0;

// Static strings for message frame IDs
static char str_odom[] = "odom";
static char str_base[] = "base_footprint";
static char str_imu[]  = "imu_link";

// ── Setup ─────────────────────────────────────────────────────────
void setup() {
    // Motor direction pins
    pinMode(AIN1, OUTPUT); pinMode(AIN2, OUTPUT);
    pinMode(BIN1, OUTPUT); pinMode(BIN2, OUTPUT);

    // PWM — espressif32 6.x / Arduino 3.x ledcAttach API
    ledcAttach(PWMA, 1000, 8);   // 1kHz, 8-bit (0–255)
    ledcAttach(PWMB, 1000, 8);

    // Encoder inputs — no pullups (encoder outputs are push-pull)
    pinMode(ENC_L_A, INPUT); pinMode(ENC_L_B, INPUT);
    pinMode(ENC_R_A, INPUT); pinMode(ENC_R_B, INPUT);
    attachInterrupt(ENC_L_A, isr_enc_l, CHANGE);
    attachInterrupt(ENC_R_A, isr_enc_r, CHANGE);

    // BNO055
    Wire.begin(I2C_SDA, I2C_SCL);
    bno.begin();
    bno.setExtCrystalUse(true);

    // micro-ROS — USB serial transport (GPIO1/3, 115200)
    set_microros_transports();
    delay(2000);    // let transport settle before agent handshake

    allocator = rcl_get_default_allocator();
    RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
    RCCHECK(rclc_node_init_default(&node, "esp32_robot", "", &support));

    RCCHECK(rclc_publisher_init_default(&pub_odom, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(nav_msgs, msg, Odometry),
        "/diff_cont/odom"));
    RCCHECK(rclc_publisher_init_default(&pub_imu, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, Imu),
        "/imu/imu"));
    RCCHECK(rclc_subscription_init_default(&sub_cmd, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Twist),
        "/diff_cont/cmd_vel_unstamped"));

    RCCHECK(rclc_executor_init(&executor, &support.context, 1, &allocator));
    RCCHECK(rclc_executor_add_subscription(&executor, &sub_cmd, &cmd_msg,
        &cmd_cb, ON_NEW_DATA));

    // Sync ESP32 clock to agent (agent must be running before setup completes)
    rmw_uros_sync_session(1000);

    // Static frame IDs
    odom_msg.header.frame_id = { str_odom, strlen(str_odom), strlen(str_odom) + 1 };
    odom_msg.child_frame_id  = { str_base, strlen(str_base), strlen(str_base) + 1 };
    imu_msg.header.frame_id  = { str_imu,  strlen(str_imu),  strlen(str_imu)  + 1 };

    // orientation_covariance[0] = -1 signals EKF to ignore orientation from this message
    // (matches current ekf.yaml config: orientation disabled, magnetometer unreliable)
    imu_msg.orientation_covariance[0] = -1.0;

    // Angular velocity covariance — diagonal, BNO055 gyro noise ~0.014 deg/s RMS
    imu_msg.angular_velocity_covariance[0] = 0.001;
    imu_msg.angular_velocity_covariance[4] = 0.001;
    imu_msg.angular_velocity_covariance[8] = 0.001;

    // Linear acceleration covariance — diagonal, BNO055 accel noise ~150 µg RMS
    imu_msg.linear_acceleration_covariance[0] = 0.01;
    imu_msg.linear_acceleration_covariance[4] = 0.01;
    imu_msg.linear_acceleration_covariance[8] = 0.01;
}

// ── Loop ──────────────────────────────────────────────────────────
static uint32_t t_control = 0;
static uint32_t t_publish = 0;

void loop() {
    rclc_executor_spin_some(&executor, RCL_MS_TO_NS(1));

    uint32_t now = millis();

    // Control + odometry @ 30 Hz
    if (now - t_control >= 33) {
        float dt = (now - t_control) * 0.001f;
        t_control = now;

        // Atomic encoder read
        noInterrupts();
        long l = enc_l;
        long r = enc_r;
        interrupts();

        long dl = l - prev_l;
        long dr = r - prev_r;
        prev_l = l;
        prev_r = r;

        float vel_l = (float)dl * COUNTS_TO_RAD / dt;   // rad/s
        float vel_r = (float)dr * COUNTS_TO_RAD / dt;

        // Differential drive odometry
        float dist_l = (float)dl * COUNTS_TO_RAD * WHEEL_RADIUS;
        float dist_r = (float)dr * COUNTS_TO_RAD * WHEEL_RADIUS;
        float dist   = (dist_l + dist_r) * 0.5f;
        float dth    = (dist_r - dist_l) / WHEEL_SEP;
        odom_x  += dist * cosf(odom_th + dth * 0.5f);
        odom_y  += dist * sinf(odom_th + dth * 0.5f);
        odom_th += dth;

        // Twist for odom message
        odom_msg.twist.twist.linear.x  = (vel_l + vel_r) * 0.5f * WHEEL_RADIUS;
        odom_msg.twist.twist.angular.z = (vel_r - vel_l) * WHEEL_RADIUS / WHEEL_SEP;

        motor_set(PWMB, BIN1, BIN2, pid_compute(pid_l, vel_l, dt));
        motor_set(PWMA, AIN1, AIN2, pid_compute(pid_r, vel_r, dt));
    }

    // Publish odom + IMU @ 20 Hz
    if (now - t_publish >= 50) {
        t_publish = now;

        int64_t ts = rmw_uros_epoch_nanos();
        int32_t  sec = (int32_t)(ts / 1000000000LL);
        uint32_t ns  = (uint32_t)(ts % 1000000000LL);

        // Odometry
        odom_msg.header.stamp.sec     = sec;
        odom_msg.header.stamp.nanosec = ns;
        odom_msg.pose.pose.position.x = odom_x;
        odom_msg.pose.pose.position.y = odom_y;
        odom_msg.pose.pose.orientation.z = sinf(odom_th * 0.5f);
        odom_msg.pose.pose.orientation.w = cosf(odom_th * 0.5f);
        rcl_publish(&pub_odom, &odom_msg, NULL);

        // IMU
        imu_msg.header.stamp.sec     = sec;
        imu_msg.header.stamp.nanosec = ns;
        imu::Quaternion q  = bno.getQuat();
        imu::Vector<3>  av = bno.getVector(Adafruit_BNO055::VECTOR_GYROSCOPE);
        imu::Vector<3>  la = bno.getVector(Adafruit_BNO055::VECTOR_LINEARACCEL);
        imu_msg.orientation.x         = q.x();
        imu_msg.orientation.y         = q.y();
        imu_msg.orientation.z         = q.z();
        imu_msg.orientation.w         = q.w();
        imu_msg.angular_velocity.x    = av.x();
        imu_msg.angular_velocity.y    = av.y();
        imu_msg.angular_velocity.z    = av.z();
        imu_msg.linear_acceleration.x = la.x();
        imu_msg.linear_acceleration.y = la.y();
        imu_msg.linear_acceleration.z = la.z();
        rcl_publish(&pub_imu, &imu_msg, NULL);
    }
}
