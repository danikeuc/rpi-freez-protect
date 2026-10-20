#include <cassert>

#include "dial_button.h"

namespace {

void test_short_press_emits_primary_action_on_release() {
  DialButton button;
  assert(button.update(true, 100) == InputEvent::None);
  assert(button.update(false, 500) == InputEvent::PrimaryAction);
}

void test_two_second_hold_emits_one_safety_drain_before_release() {
  DialButton button;
  assert(button.update(true, 100) == InputEvent::None);
  assert(button.update(true, 2099) == InputEvent::None);
  assert(button.update(true, 2100) == InputEvent::SafetyDrain);
  assert(button.update(true, 2500) == InputEvent::None);
  assert(button.update(false, 2600) == InputEvent::None);
}

}  // namespace

#ifdef PIO_UNIT_TESTING
#include <unity.h>

extern "C" void setUp(void) {}
extern "C" void tearDown(void) {}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_short_press_emits_primary_action_on_release);
  RUN_TEST(test_two_second_hold_emits_one_safety_drain_before_release);
  return UNITY_END();
}
#else
int main() {
  test_short_press_emits_primary_action_on_release();
  test_two_second_hold_emits_one_safety_drain_before_release();
}
#endif
