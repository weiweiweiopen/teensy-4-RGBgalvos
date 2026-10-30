#include <Audio.h>
#include <Wire.h>

AudioInputUSBOct usbInput;
AudioOutputTDM tdmOutput;

// CS42448 uses the first 16 bits of each 32-bit TDM slot.
AudioConnection patchCord1(usbInput, 0, tdmOutput, 0);
AudioConnection patchCord2(usbInput, 1, tdmOutput, 2);
AudioConnection patchCord3(usbInput, 2, tdmOutput, 4);
AudioConnection patchCord4(usbInput, 3, tdmOutput, 6);
AudioConnection patchCord5(usbInput, 4, tdmOutput, 8);
AudioConnection patchCord6(usbInput, 5, tdmOutput, 10);
AudioConnection patchCord7(usbInput, 6, tdmOutput, 12);
AudioConnection patchCord8(usbInput, 7, tdmOutput, 14);

bool codecReady = false;
uint8_t codecAddress = 0;
uint8_t codecInitStep = 0;
uint8_t codecWireStatus = 0;
uint8_t wireAddresses[16] = {};
uint8_t wireDeviceCount = 0;
uint8_t wire1Addresses[16] = {};
uint8_t wire1DeviceCount = 0;

void scanI2C(TwoWire &bus, uint8_t *addresses, uint8_t &deviceCount) {
  uint8_t acknowledgements[127] = {};
  deviceCount = 0;

  for (uint8_t pass = 0; pass < 3; ++pass) {
    for (uint8_t address = 1; address < 127; ++address) {
      bus.beginTransmission(address);
      if (bus.endTransmission() == 0) {
        ++acknowledgements[address];
      }
      delayMicroseconds(50);
    }
  }

  for (uint8_t address = 1; address < 127; ++address) {
    if (acknowledgements[address] == 3 && deviceCount < 16) {
      addresses[deviceCount++] = address;
    }
  }
}

uint8_t writeCodecRegister(uint8_t address, uint8_t reg, uint8_t value) {
  Wire1.beginTransmission(address);
  Wire1.write(reg);
  Wire1.write(value);
  return Wire1.endTransmission();
}

uint8_t writeCodecRegisters(uint8_t address, uint8_t reg,
                            const uint8_t *data, size_t length) {
  Wire1.beginTransmission(address);
  Wire1.write(reg | 0x80);
  Wire1.write(data, length);
  return Wire1.endTransmission();
}

bool enableCodec(uint8_t address) {
  static const uint8_t config[] = {
    0xF4, // Functional mode: slave, MCLK up to 25.6 MHz
    0x76, // Interface format: TDM
    0x1C, // ADC control and DAC de-emphasis
    0x63, // Soft volume transitions
    0xFF  // Mute all DAC channels during startup
  };
  static const uint8_t unmuteAndVolume[] = {
    0x00, // Unmute all DAC channels
    0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03
  };

  codecInitStep = 1;
  codecWireStatus = writeCodecRegister(address, 0x02, 0xFF);
  if (codecWireStatus != 0) {
    return false;
  }
  codecInitStep = 2;
  codecWireStatus = writeCodecRegisters(address, 0x03, config, sizeof(config));
  if (codecWireStatus != 0) {
    return false;
  }
  codecInitStep = 3;
  codecWireStatus = writeCodecRegister(address, 0x02, 0x00);
  if (codecWireStatus != 0) {
    return false;
  }
  delay(50);
  codecInitStep = 4;
  codecWireStatus = writeCodecRegisters(address, 0x07, unmuteAndVolume,
                                        sizeof(unmuteAndVolume));
  return codecWireStatus == 0;
}

void printI2CAddresses(const uint8_t *addresses, uint8_t deviceCount) {
  if (deviceCount == 0) {
    Serial.print("none");
  } else {
    for (uint8_t i = 0; i < deviceCount; ++i) {
      Serial.printf("%s0x%02X", i == 0 ? "" : ",", addresses[i]);
    }
  }
}

uint8_t findCodecAddress() {
  for (uint8_t i = 0; i < wire1DeviceCount; ++i) {
    if (wire1Addresses[i] >= 0x48 && wire1Addresses[i] <= 0x4B) {
      return wire1Addresses[i];
    }
  }
  return 0;
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  AudioMemory(80);

  delay(100);
  Wire.begin();
  Wire1.begin();
  scanI2C(Wire, wireAddresses, wireDeviceCount);
  scanI2C(Wire1, wire1Addresses, wire1DeviceCount);
  codecAddress = findCodecAddress();
  if (codecAddress != 0) {
    codecReady = enableCodec(codecAddress);
  }

  Serial.printf("USB -> CS42448 TDM test: %d channels, %.1f Hz\n",
                USB_AUDIO_NO_CHANNELS_480, AUDIO_SAMPLE_RATE_EXACT);
  Serial.println(codecReady ? "CS42448 ready" : "CS42448 I2C setup failed");
}

void loop() {
  static uint32_t lastLedChange = 0;
  static uint32_t lastReport = 0;
  static bool ledOn = false;
  const uint32_t now = millis();
  const uint32_t blinkInterval = codecReady ? 500 : 100;

  if (now - lastLedChange >= blinkInterval) {
    lastLedChange = now;
    ledOn = !ledOn;
    digitalWrite(LED_BUILTIN, ledOn);
  }

  if (now - lastReport >= 1000) {
    lastReport = now;
    Serial.printf("codec=%s", codecReady ? "ready" : "failed");
    if (codecAddress != 0) {
      Serial.printf("@0x%02X", codecAddress);
    }
    if (!codecReady && codecInitStep != 0) {
      Serial.printf("(step=%u,status=%u)", codecInitStep, codecWireStatus);
    }
    Serial.print(", Wire=");
    printI2CAddresses(wireAddresses, wireDeviceCount);
    Serial.print(", Wire1=");
    printI2CAddresses(wire1Addresses, wire1DeviceCount);
    Serial.printf(", audio memory=%u/%u, cpu=%.1f%%\n",
                  AudioMemoryUsage(), AudioMemoryUsageMax(),
                  AudioProcessorUsage());
  }
}
