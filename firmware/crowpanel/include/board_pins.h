#pragma once

#include <cstdint>

namespace BoardPins {
inline constexpr std::int8_t kTouchSda = 6;
inline constexpr std::int8_t kTouchScl = 7;
inline constexpr std::int8_t kDisplaySclk = 10;
inline constexpr std::int8_t kDisplayMosi = 11;
inline constexpr std::int8_t kTouchReset = 13;
inline constexpr std::int8_t kDisplayDc = 3;
inline constexpr std::int8_t kTouchInterrupt = 5;
inline constexpr std::int8_t kDisplayCs = 9;
inline constexpr std::int8_t kDisplayReset = 14;
inline constexpr std::int8_t kPowerEnableOne = 1;
inline constexpr std::int8_t kPowerEnableTwo = 2;
inline constexpr std::int8_t kEncoderA = 45;
inline constexpr std::int8_t kEncoderB = 42;
inline constexpr std::int8_t kEncoderButton = 41;
inline constexpr std::int8_t kBacklight = 46;
inline constexpr std::uint16_t kDisplayWidth = 240;
inline constexpr std::uint16_t kDisplayHeight = 240;
}  // namespace BoardPins

static_assert(BoardPins::kEncoderA == 45);
static_assert(BoardPins::kEncoderB == 42);
static_assert(BoardPins::kEncoderButton == 41);
