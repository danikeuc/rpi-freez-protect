#include "dial_button.h"

namespace {
constexpr std::uint32_t kSafetyHoldMs = 2000;
}

InputEvent DialButton::update(bool pressed, std::uint32_t now_ms) {
  if (pressed && !pressed_) {
    pressed_ = true;
    long_press_emitted_ = false;
    pressed_at_ms_ = now_ms;
    return InputEvent::None;
  }
  if (pressed && pressed_ && !long_press_emitted_ &&
      now_ms - pressed_at_ms_ >= kSafetyHoldMs) {
    long_press_emitted_ = true;
    return InputEvent::SafetyDrain;
  }
  if (!pressed && pressed_) {
    pressed_ = false;
    return long_press_emitted_ ? InputEvent::None : InputEvent::PrimaryAction;
  }
  return InputEvent::None;
}
