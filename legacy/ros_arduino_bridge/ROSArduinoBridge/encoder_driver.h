/* *************************************************************
   Encoder driver function definitions - by James Nugen
   ************************************************************ */
   
   
#ifdef ARDUINO_ENC_COUNTER
  #define LEFT_ENC_PIN_A  2   // D2 - INT0
  #define LEFT_ENC_PIN_B  4   // D4
  #define RIGHT_ENC_PIN_A 3   // D3 - INT1
  #define RIGHT_ENC_PIN_B 12  // D12
#endif

long readEncoder(int i);
void resetEncoder(int i);
void resetEncoders();
void leftEncoderISR();
void rightEncoderISR();

