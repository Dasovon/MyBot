/***************************************************************
   Motor driver function definitions - by James Nugen
   *************************************************************/

#ifdef L298_MOTOR_DRIVER
  #define LEFT_MOTOR_ENABLE    5   // ENA - PWM
  #define LEFT_MOTOR_FORWARD   7   // IN2 (swapped)
  #define LEFT_MOTOR_BACKWARD  6   // IN1 (swapped)
  #define RIGHT_MOTOR_FORWARD  9   // IN4 (swapped)
  #define RIGHT_MOTOR_BACKWARD 8   // IN3 (swapped)
  #define RIGHT_MOTOR_ENABLE   10  // ENB - PWM
#endif

#ifdef TB6612_MOTOR_DRIVER
  #define LEFT_MOTOR_ENABLE    5   // PWMA
  #define LEFT_MOTOR_FORWARD   7   // AIN1
  #define LEFT_MOTOR_BACKWARD  6   // AIN2
  #define RIGHT_MOTOR_FORWARD  9   // BIN2
  #define RIGHT_MOTOR_BACKWARD 8   // BIN1
  #define RIGHT_MOTOR_ENABLE   10  // PWMB
#endif

void initMotorController();
void setMotorSpeed(int i, int spd);
void setMotorSpeeds(int leftSpeed, int rightSpeed);

