#pragma once

#include "dial_button.h"
#include "display_types.h"

class HardwareUi {
 public:
  void begin();
  void render(const DisplayModel& model);
  InputEvent poll_input();
  void tick();
};
