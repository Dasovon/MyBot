/* *************************************************************
   Encoder definitions
   
   Add an "#ifdef" block to this file to include support for
   a particular encoder board or library. Then add the appropriate
   #define near the top of the main ROSArduinoBridge.ino file.
   
   ************************************************************ */
   
#ifdef USE_BASE

#ifdef ROBOGAIA
  /* The Robogaia Mega Encoder shield */
  #include "MegaEncoderCounter.h"

  /* Create the encoder shield object */
  MegaEncoderCounter encoders = MegaEncoderCounter(4); // Initializes the Mega Encoder Counter in the 4X Count mode
  
  /* Wrap the encoder reading function */
  long readEncoder(int i) {
    if (i == LEFT) return encoders.YAxisGetCount();
    else return encoders.XAxisGetCount();
  }

  /* Wrap the encoder reset function */
  void resetEncoder(int i) {
    if (i == LEFT) return encoders.YAxisReset();
    else return encoders.XAxisReset();
  }
#elif defined(ARDUINO_ENC_COUNTER)
  volatile long left_enc_pos = 0L;
  volatile long right_enc_pos = 0L;

  /* LEFT encoder ISR - triggered on any change of D2 (INT0)
     Reads B signal from D4 to determine direction */
  void leftEncoderISR() {
    if (digitalRead(LEFT_ENC_PIN_A) == digitalRead(LEFT_ENC_PIN_B))
      left_enc_pos++;
    else
      left_enc_pos--;
  }

  /* RIGHT encoder ISR - triggered on any change of D3 (INT1)
     Reads B signal from D12 to determine direction */
  void rightEncoderISR() {
    if (digitalRead(RIGHT_ENC_PIN_A) != digitalRead(RIGHT_ENC_PIN_B))
      right_enc_pos++;
    else
      right_enc_pos--;
  }

  /* Wrap the encoder reading function */
  long readEncoder(int i) {
    if (i == LEFT) return left_enc_pos;
    else return right_enc_pos;
  }

  /* Wrap the encoder reset function */
  void resetEncoder(int i) {
    if (i == LEFT) {
      left_enc_pos = 0L;
      return;
    } else {
      right_enc_pos = 0L;
      return;
    }
  }
#else
  #error A encoder driver must be selected!
#endif

/* Wrap the encoder reset function */
void resetEncoders() {
  resetEncoder(LEFT);
  resetEncoder(RIGHT);
}

#endif

