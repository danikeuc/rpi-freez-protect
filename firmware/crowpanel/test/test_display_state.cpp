#include <cassert>
#include <string>

#include "display_state.h"
#include "hub_client.h"

namespace {

HubStatus healthy_status() {
  HubStatus status{};
  status.state = "FROST_PROTECTION";
  status.reason = "sensor_pending";
  status.has_pipe_temperature = false;
  status.sensor_health = "CALIBRATION_REQUIRED";
  status.forecast.available = true;
  status.forecast.fresh = true;
  status.forecast.dates[0] = "2026-09-11";
  status.forecast.minima_c[0] = 8.0F;
  status.action = DisplayAction::TimedShower;
  status.action_enabled = true;
  return status;
}

void test_offline_disables_actions_and_shows_required_copy() {
  const DisplayModel model = reduce_status(healthy_status(), true, false);
  assert(!model.action_enabled);
  assert(model.connection_text == "NI POVEZAVE — PREVERI HUB");
  assert(next_action(model) == DisplayAction::None);
}

void test_active_timer_maps_primary_action_to_immediate_drain() {
  HubStatus status = healthy_status();
  status.state = "TIMED_SHOWER";
  status.action = DisplayAction::CloseNow;
  const DisplayModel model = reduce_status(status, true, true);
  assert(model.action_enabled);
  assert(model.primary_action_text == "ZAPRI TAKOJ");
  assert(next_action(model) == DisplayAction::CloseNow);
}

void test_missing_sensor_maps_to_slovenian_pending_copy() {
  const DisplayModel model = reduce_status(healthy_status(), true, true);
  assert(model.pipe_temperature_text == "SENZOR ČAKA");
  assert(model.primary_action_text == "TUŠ 10 MIN");
}

void test_action_paths_are_display_api_only() {
  assert(std::string(HubClient::kTimedShowerPath) ==
         "/api/v1/display/actions/timed-shower");
  assert(std::string(HubClient::kDrainPath) == "/api/v1/display/actions/drain");
}

void test_encoder_navigation_has_exactly_two_pages() {
  assert(move_page(DisplayPage::Home, true) == DisplayPage::Forecast);
  assert(move_page(DisplayPage::Forecast, false) == DisplayPage::Home);
}

}  // namespace

#ifdef PIO_UNIT_TESTING
#include <unity.h>

void test_offline() { test_offline_disables_actions_and_shows_required_copy(); }
void test_active_timer() { test_active_timer_maps_primary_action_to_immediate_drain(); }
void test_missing_sensor() { test_missing_sensor_maps_to_slovenian_pending_copy(); }
void test_action_paths() { test_action_paths_are_display_api_only(); }
void test_navigation() { test_encoder_navigation_has_exactly_two_pages(); }

void setup() {
  UNITY_BEGIN();
  RUN_TEST(test_offline);
  RUN_TEST(test_active_timer);
  RUN_TEST(test_missing_sensor);
  RUN_TEST(test_action_paths);
  RUN_TEST(test_navigation);
  UNITY_END();
}

void loop() {}
#else
int main() {
  test_offline_disables_actions_and_shows_required_copy();
  test_active_timer_maps_primary_action_to_immediate_drain();
  test_missing_sensor_maps_to_slovenian_pending_copy();
  test_action_paths_are_display_api_only();
  test_encoder_navigation_has_exactly_two_pages();
}
#endif
