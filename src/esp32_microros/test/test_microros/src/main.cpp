#include <Arduino.h>
#include <micro_ros_arduino.h>

#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <std_msgs/msg/int32.h>
#include <geometry_msgs/msg/twist.h>

// LED on GPIO2 (built-in on most ESP32-DevKitC — strapping pin, safe after boot)
#define LED_PIN  2

// Agent connection states
enum State { WAITING, CONNECTED };
static State state = WAITING;

static rcl_publisher_t    pub_heartbeat;
static rcl_subscription_t sub_cmd;
static std_msgs__msg__Int32      hb_msg;
static geometry_msgs__msg__Twist cmd_msg;

static rclc_executor_t executor;
static rcl_allocator_t allocator;
static rclc_support_t  support;
static rcl_node_t      node;

static int32_t counter = 0;
static bool    cmd_received = false;
static float   last_linear = 0, last_angular = 0;

static void cmd_cb(const void* msg) {
    const auto* m = (const geometry_msgs__msg__Twist*)msg;
    last_linear  = m->linear.x;
    last_angular = m->angular.z;
    cmd_received = true;
}

static bool create_entities() {
    allocator = rcl_get_default_allocator();
    if (rclc_support_init(&support, 0, NULL, &allocator) != RCL_RET_OK) return false;
    if (rclc_node_init_default(&node, "esp32_test", "", &support) != RCL_RET_OK) return false;

    if (rclc_publisher_init_default(&pub_heartbeat, &node,
            ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32),
            "/esp32/heartbeat") != RCL_RET_OK) return false;

    if (rclc_subscription_init_default(&sub_cmd, &node,
            ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Twist),
            "/diff_cont/cmd_vel_unstamped") != RCL_RET_OK) return false;

    if (rclc_executor_init(&executor, &support.context, 1, &allocator) != RCL_RET_OK) return false;
    if (rclc_executor_add_subscription(&executor, &sub_cmd, &cmd_msg,
            &cmd_cb, ON_NEW_DATA) != RCL_RET_OK) return false;

    return true;
}

static void destroy_entities() {
    rmw_context_t* rmw_ctx = rcl_context_get_rmw_context(&support.context);
    (void)rmw_uros_set_context_entity_destroy_session_timeout(rmw_ctx, 0);
    rcl_publisher_fini(&pub_heartbeat, &node);
    rcl_subscription_fini(&sub_cmd, &node);
    rclc_executor_fini(&executor);
    rcl_node_fini(&node);
    rclc_support_fini(&support);
}

void setup() {
    pinMode(LED_PIN, OUTPUT);
    set_microros_transports();
    // No Serial debug — UART0 is used by micro-ROS transport.
    // Monitor connection via LED and Pi-side topic echo.
}

static uint32_t t_heartbeat = 0;
static uint32_t t_blink     = 0;
static bool     led_state   = false;

void loop() {
    uint32_t now = millis();

    switch (state) {
        case WAITING:
            // Fast blink (200ms) while waiting for agent
            if (now - t_blink >= 200) {
                t_blink   = now;
                led_state = !led_state;
                digitalWrite(LED_PIN, led_state);
            }
            if (rmw_uros_ping_agent(100, 1) == RMW_RET_OK) {
                if (create_entities()) {
                    rmw_uros_sync_session(1000);
                    counter = 0;
                    state = CONNECTED;
                    digitalWrite(LED_PIN, HIGH);  // solid = connected
                }
            }
            break;

        case CONNECTED:
            rclc_executor_spin_some(&executor, RCL_MS_TO_NS(1));

            // Heartbeat at 1 Hz
            if (now - t_heartbeat >= 1000) {
                t_heartbeat = now;
                hb_msg.data = ++counter;
                rcl_publish(&pub_heartbeat, &hb_msg, NULL);

                // Slow blink (1Hz) while connected to show activity
                led_state = !led_state;
                digitalWrite(LED_PIN, led_state);
            }

            // Check agent is still alive
            if (rmw_uros_ping_agent(100, 1) != RMW_RET_OK) {
                destroy_entities();
                state = WAITING;
                digitalWrite(LED_PIN, LOW);
            }
            break;
    }
}

// ── How to verify on Pi ───────────────────────────────────────────
//
// 1. Start agent:
//    ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0
//
// 2. Confirm heartbeat (should increment every second):
//    ros2 topic echo /esp32/heartbeat
//
// 3. Confirm ESP32 can receive commands:
//    ros2 topic pub --rate 2 /diff_cont/cmd_vel_unstamped \
//      geometry_msgs/msg/Twist '{linear: {x: 0.1}, angular: {z: 0.0}}'
//    LED blink rate unchanged (no Serial output) — check agent log for subscriber activity.
//
// 4. List all ESP32 topics:
//    ros2 topic list | grep esp32
//
// PASS criteria:
//   - /esp32/heartbeat visible and incrementing
//   - No errors in micro_ros_agent output
//   - LED: fast blink = waiting, slow blink = connected
