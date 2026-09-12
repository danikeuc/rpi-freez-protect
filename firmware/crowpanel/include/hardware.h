#pragma once

#include "display_types.h"

enum class InputEvent { None, NextPage, PreviousPage, PrimaryAction };

class HardwareUi {
 public:
  void begin();
  void render(const DisplayModel& model);
  InputEvent poll_input();
  void tick();
};
