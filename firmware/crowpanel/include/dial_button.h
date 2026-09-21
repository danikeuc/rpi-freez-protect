#pragma once

#include <cstdint>

enum class InputEvent { None, NextPage, PreviousPage, PrimaryAction, SafetyDrain };

class DialButton {
 public:
  InputEvent update(bool pressed, std::uint32_t now_ms);

 private:
  bool pressed_ = false;
  bool long_press_emitted_ = false;
  std::uint32_t pressed_at_ms_ = 0;
};
