#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoOTA.h>
#include <TelnetStream.h>
#include <micro_ros_arduino.h>
#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <std_msgs/msg/int32.h>
#include <geometry_msgs/msg/twist.h>
#include "credentials.h"

// micro-ROS agent — Pi IP and UDP port
#define AGENT_IP    "192.168.86.33"
#define AGENT_PORT  8888

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

static int32_t counter      = 0;
static float   last_linear  = 0, last_angular = 0;
static bool    cmd_received = false;

template<typename... Args>
static void log(const char* fmt, Args... args) {
    char buf[256];
    snprintf(buf, sizeof(buf), fmt, args...);
    Serial.print(buf);
    TelnetStream.print(buf);
}

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
    Serial.println("[OTA] Ready");
}

void setup() {
    Serial.begin(115200);
    delay(500);

    wifi_setup();
    ota_setup();
    TelnetStream.begin();
    Serial.println("[Telnet] port 23 — connect: nc 192.168.86.43 23");

    // WiFi UDP transport to Pi agent
    set_microros_wifi_transports(WIFI_SSID, WIFI_PASSWORD, AGENT_IP, AGENT_PORT);

    log("[microROS] Waiting for agent at %s:%d...\n", AGENT_IP, AGENT_PORT);
}

static uint32_t t_heartbeat = 0;

void loop() {
    ArduinoOTA.handle();

    uint32_t now = millis();

    switch (state) {
        case WAITING:
            if (rmw_uros_ping_agent(100, 1) == RMW_RET_OK) {
                if (create_entities()) {
                    rmw_uros_sync_session(1000);
                    counter = 0;
                    state = CONNECTED;
                    log("[microROS] Connected to agent!\n");
                    log("Monitor: ros2 topic echo /esp32/heartbeat\n");
                }
            }
            break;

        case CONNECTED:
            rclc_executor_spin_some(&executor, RCL_MS_TO_NS(1));

            if (now - t_heartbeat >= 1000) {
                t_heartbeat = now;
                hb_msg.data = ++counter;
                rcl_publish(&pub_heartbeat, &hb_msg, NULL);
                log("[HB] %ld", (long)counter);
                if (cmd_received) {
                    log("  cmd_vel: linear=%.3f angular=%.3f", last_linear, last_angular);
                    cmd_received = false;
                }
                log("\n");
            }

            if (rmw_uros_ping_agent(100, 1) != RMW_RET_OK) {
                destroy_entities();
                state = WAITING;
                log("[microROS] Agent lost — reconnecting...\n");
            }
            break;
    }
}
