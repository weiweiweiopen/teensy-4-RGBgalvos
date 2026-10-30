#include <Audio.h>
#include <Wire.h>
#include "calibration.h"

// Requires the project's pinned alex6679 UAC2 core (8 channels), Teensyduino 1.59.
// RevB-P4: hardware-qualified reset/ARM, isolated DAC and ADC inputs.
constexpr uint8_t RESET_PIN = 2;
constexpr uint8_t INT_PIN = 3;
constexpr uint8_t HEART_PIN = 4;
constexpr uint8_t RAILS_GOOD_PIN = 5;
constexpr uint8_t ARM_PIN = 6;
constexpr uint8_t MUTEC_PIN = 9;
constexpr uint8_t POS_SENSE = A0; // GPIO14
constexpr uint8_t NEG_SENSE = A1; // GPIO15
constexpr uint8_t CODEC = 0x48;
constexpr uint32_t STREAM_TIMEOUT_US = 20000;
constexpr float POS_SENSE_FACTOR = 6.0f + 100.0f / 4.7f;
constexpr float NEG_SENSE_FACTOR = 11.0f + 100.0f / 4.7f;

AudioInputUSBOct usbInput;
volatile uint32_t lastCompleteBlockUs = 0;
volatile uint32_t completeBlocks = 0;
volatile bool blockHealthy = false;
volatile bool outputRequested = false;

class ILDAConditioner : public AudioStream {
 public:
  ILDAConditioner() : AudioStream(8, queue) {}
  void update() override {
    audio_block_t *blocks[8];
    bool complete = true;
    for (unsigned ch = 0; ch < 8; ++ch) {
      blocks[ch] = receiveWritable(ch);
      complete = complete && blocks[ch] != nullptr;
    }
    const auto status = usbInput.getStatus();
    complete = complete && status.receivingData && status.usb_high_speed &&
               status.num_transmitted_channels == 8;
    blockHealthy = complete;
    if (complete) {
      lastCompleteBlockUs = micros();
      ++completeBlocks;
    }
    for (unsigned ch = 0; ch < 8; ++ch) {
      if (!blocks[ch]) continue; // TDM substitutes zero for a missing channel.
      for (unsigned i = 0; i < AUDIO_BLOCK_SAMPLES; ++i) {
        int32_t sample = blocks[ch]->data[i];
        if (ch >= 2 && sample < 0) sample = 0; // Colours use 0..+32767 PCM.
        sample = static_cast<int32_t>((static_cast<int64_t>(sample) *
                                     channelGainQ16[ch]) / 65536) +
                 channelOffsetCodes[ch];
        if (sample > 32767) sample = 32767;
        if (sample < (ch >= 2 ? 0 : -32768)) sample = ch >= 2 ? 0 : -32768;
        blocks[ch]->data[i] = complete && outputRequested ? sample : 0;
      }
      transmit(blocks[ch], ch);
      release(blocks[ch]);
    }
  }
 private:
  audio_block_t *queue[8];
};

ILDAConditioner conditioner;
AudioOutputTDM tdm;
AudioConnection c0(usbInput, 0, conditioner, 0);
AudioConnection c1(usbInput, 1, conditioner, 1);
AudioConnection c2(usbInput, 2, conditioner, 2);
AudioConnection c3(usbInput, 3, conditioner, 3);
AudioConnection c4(usbInput, 4, conditioner, 4);
AudioConnection c5(usbInput, 5, conditioner, 5);
AudioConnection c6(usbInput, 6, conditioner, 6);
AudioConnection c7(usbInput, 7, conditioner, 7);
AudioConnection o0(conditioner, 0, tdm, 0);
AudioConnection o1(conditioner, 1, tdm, 2);
AudioConnection o2(conditioner, 2, tdm, 4);
AudioConnection o3(conditioner, 3, tdm, 6);
AudioConnection o4(conditioner, 4, tdm, 8);
AudioConnection o5(conditioner, 5, tdm, 10);
AudioConnection o6(conditioner, 6, tdm, 12);
AudioConnection o7(conditioner, 7, tdm, 14);

bool codecReady = false;
bool railsGood = false;
bool clockGood = false;
volatile bool armed = false;
bool manualEnable = false;
volatile bool railLossLatched = true;
uint32_t railsStableSinceMs = 0;
uint32_t lastInitAttemptMs = 0;
uint32_t lastCodecCheckMs = 0;
float positiveRail = 0, negativeRailMagnitude = 0;

bool writeCodec(uint8_t reg, uint8_t value) {
  Wire1.beginTransmission(CODEC);
  Wire1.write(reg);
  Wire1.write(value);
  return Wire1.endTransmission() == 0;
}

bool readCodec(uint8_t reg, uint8_t &value) {
  Wire1.beginTransmission(CODEC);
  Wire1.write(reg);
  if (Wire1.endTransmission() != 0) return false;
  if (Wire1.requestFrom(CODEC, static_cast<uint8_t>(1)) != 1) return false;
  value = Wire1.read();
  return true;
}

void disconnectOutputs() {
  const bool wasRequested = armed || outputRequested;
  digitalWriteFast(ARM_PIN, LOW); // Prepare the next fresh ARM clock edge.
  digitalWriteFast(HEART_PIN, LOW);
  outputRequested = false;
  armed = false;
  if (wasRequested) {
    digitalWriteFast(RESET_PIN, LOW); // Asynchronously clears U8, U4 and output eligibility.
    codecReady = false;
    clockGood = false;
  }
}

void hardwareRailLost() {
  // No I2C or Serial in the ISR. Hardware has already inhibited ARM/reset.
  digitalWriteFast(ARM_PIN, LOW);
  digitalWriteFast(HEART_PIN, LOW);
  digitalWriteFast(RESET_PIN, LOW);
  outputRequested = false;
  armed = false;
  railLossLatched = true;
}

bool initializeCodec() {
  if (!digitalReadFast(RAILS_GOOD_PIN)) return false;
  digitalWriteFast(RESET_PIN, LOW);
  delay(5); // DS648F5 p18: at least 1 ms low with supplies/clocks settled.
  digitalWriteFast(RESET_PIN, HIGH);
  delay(2);
  uint8_t id = 0;
  if (!readCodec(0x01, id) || (id & 0xF0) != 0 || (id & 0x0F) == 0) return false;
  if (!writeCodec(0x02, 0xFF)) return false;
  // Teensy AudioOutputTDM generates MCLK = 512 Fs, BCLK = 256 Fs.
  const uint8_t mode = AUDIO_SAMPLE_RATE_EXACT > 50000.0f ? 0xF8 : 0xF4;
  if (!writeCodec(0x03, mode) || !writeCodec(0x04, 0x76) ||
      !writeCodec(0x05, 0x00) || !writeCodec(0x06, 0x00) ||
      !writeCodec(0x07, 0xFF) || !writeCodec(0x10, 0x00)) return false;
  for (uint8_t reg = 0x08; reg <= 0x0F; ++reg)
    if (!writeCodec(reg, 0x00)) return false; // 0 dB, not old test's -1.5 dB.
  // ADCs unused and powered down; all four DAC pairs enabled.
  if (!writeCodec(0x02, 0xE0)) return false;
  delay(500);
  delay(static_cast<unsigned long>(2100.0f * 1000.0f / AUDIO_SAMPLE_RATE_EXACT + 2));
  if (!writeCodec(0x1A, 0x10) || !writeCodec(0x1B, 0x00)) return false;
  uint8_t status;
  if (!readCodec(0x19, status) || (status & 0x10)) return false;
  if (!writeCodec(0x07, 0x00)) return false;
  return digitalReadFast(RAILS_GOOD_PIN);
}

void setup() {
  digitalWrite(ARM_PIN, LOW); pinMode(ARM_PIN, OUTPUT);
  digitalWrite(HEART_PIN, LOW); pinMode(HEART_PIN, OUTPUT);
  digitalWrite(RESET_PIN, LOW); pinMode(RESET_PIN, OUTPUT);
  pinMode(INT_PIN, INPUT);
  pinMode(MUTEC_PIN, INPUT);
  pinMode(RAILS_GOOD_PIN, INPUT); // External 10k to actual Teensy 3.3V.
  attachInterrupt(digitalPinToInterrupt(RAILS_GOOD_PIN), hardwareRailLost, FALLING);
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  AudioMemory(100);
  analogReadResolution(12);
  analogReadAveraging(8);
  Wire1.begin();
  Wire1.setClock(100000); // CS42448 control port maximum is 100 kHz.
  delay(100);
  // Rail telemetry becomes available after the ADC switch's supply supervisor.
  // Initialize in loop only after both hardware and measured rails are stable.
  codecReady = false;
  Serial.println("ILDA8CH RevB-P4: send a=enable, s=stop. Rail loss requires re-arm.");
  Serial.println(calibratedForFullILDA ? "Full-range calibration installed" :
                 "Reduced-range factory defaults: calibrate before full-range use");
}

void loop() {
  static uint32_t lastHeartbeatUs = 0, lastRailMs = 0, lastReportMs = 0;
  const uint32_t nowUs = micros(), nowMs = millis();
  noInterrupts();
  const bool lostRails = railLossLatched;
  railLossLatched = false;
  interrupts();
  if (lostRails) {
    manualEnable = false;
    codecReady = false;
    clockGood = false;
    railsStableSinceMs = 0;
    disconnectOutputs();
    digitalWriteFast(RESET_PIN, LOW);
  }
  while (Serial.available()) {
    const char c = Serial.read();
    if (c == 'a') manualEnable = true;
    if (c == 's') { manualEnable = false; disconnectOutputs(); }
  }
  if (nowMs - lastRailMs >= 2) {
    lastRailMs = nowMs;
    // Teensy's ADC uses its local 3.3 V reference. Thresholds include regulator tolerance.
    const float vp = analogRead(POS_SENSE) * (3.3f / 4095.0f);
    const float vn = analogRead(NEG_SENSE) * (3.3f / 4095.0f);
    // R26 now uses actual MCU_3V3. Each ADC has a 4.7k downstream pulldown.
    positiveRail = vp * POS_SENSE_FACTOR;
    negativeRailMagnitude = 33.0f - NEG_SENSE_FACTOR * vn;
    railsGood = digitalReadFast(RAILS_GOOD_PIN) &&
                positiveRail > 12.5f && positiveRail < 17.2f &&
                 negativeRailMagnitude > 12.5f && negativeRailMagnitude < 17.2f;
    if (!railsGood) manualEnable = false; // Also latch measured UV/OV faults.
  }
  if (!digitalReadFast(RAILS_GOOD_PIN)) {
    codecReady = false;
    clockGood = false;
    railsGood = false;
    railsStableSinceMs = 0;
    manualEnable = false;
    digitalWriteFast(RESET_PIN, LOW);
  }
  if (railsGood) {
    if (!railsStableSinceMs) railsStableSinceMs = nowMs;
    if (!codecReady && nowMs - railsStableSinceMs >= 20 &&
        nowMs - lastInitAttemptMs >= 1000) {
      disconnectOutputs();
      lastInitAttemptMs = nowMs;
      codecReady = initializeCodec();
    }
  } else {
    railsStableSinceMs = 0;
  }
  if (nowMs - lastCodecCheckMs >= 10) {
    lastCodecCheckMs = nowMs;
    uint8_t status = 0;
    // MUTEC can also indicate valid zero-data states; it is diagnostic only.
    clockGood = codecReady && readCodec(0x19, status) && !(status & 0x10);
    if (codecReady && !clockGood) {
      codecReady = false;
      manualEnable = false;
      disconnectOutputs();
      digitalWriteFast(RESET_PIN, LOW);
    }
  }
  const bool streamGood = blockHealthy && completeBlocks >= 8 &&
                         (nowUs - lastCompleteBlockUs) < STREAM_TIMEOUT_US;
  if (!manualEnable || !railsGood || !clockGood || !streamGood) {
    disconnectOutputs();
  } else {
    outputRequested = true;
    digitalWriteFast(ARM_PIN, HIGH);
    if (nowUs - lastHeartbeatUs >= 1000) {
      lastHeartbeatUs = nowUs;
      digitalWriteFast(HEART_PIN, HIGH);
      delayMicroseconds(2);
      digitalWriteFast(HEART_PIN, LOW);
    }
    armed = true;
  }
  digitalWriteFast(LED_BUILTIN, armed);
  if (nowMs - lastReportMs >= 1000 && Serial) {
    lastReportMs = nowMs;
    Serial.printf("codec=%u clock=%u stream=%u rails=%.2f/-%.2f armed=%u blocks=%lu\n",
      codecReady, clockGood, streamGood, positiveRail, negativeRailMagnitude, armed,
      static_cast<unsigned long>(completeBlocks));
  }
}
