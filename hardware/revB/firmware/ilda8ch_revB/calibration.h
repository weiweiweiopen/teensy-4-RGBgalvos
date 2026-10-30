#pragma once
#include <stdint.h>

// Channel order: X, Y, R, G, B, Intensity, AUX1, AUX2.
// 65536 = unity digital gain. Start reduced; determine each value using a DMM
// at J1 with the intended projector-equivalent load, per docs/CALIBRATION.md.
// 0.70 keeps full-scale below nominal ILDA limits over CS42448 VA/gain range.
constexpr int32_t channelGainQ16[8] = {
  45875, 45875, 45875, 45875, 45875, 45875, 45875, 45875
};
constexpr int32_t channelOffsetCodes[8] = {0, 0, 0, 0, 0, 0, 0, 0};
constexpr bool calibratedForFullILDA = false;
