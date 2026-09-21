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
  for (std::size_t index = 0; index < status.forecast.dates.size(); ++index) {
    status.forecast.dates[index] = "2026-09-11";
    status.forecast.minima_c[index] = 8.0F + static_cast<float>(index);
  }
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
  assert(model.primary_action_text == "ZAPRI VODO");
  assert(next_action(model) == DisplayAction::CloseNow);
}

void test_sensor_details_are_not_exposed_on_the_home_screen() {
  const DisplayModel model = reduce_status(healthy_status(), true, true);
  assert(model.pipe_temperature_text.empty());
  assert(model.sensor_health.empty());
  assert(model.primary_action_text == "VKLOPI TUŠ");
  assert(model.primary_action_detail == "10 MIN");
  assert(model.forecast_summary_text == "7 DNI · MIN 8,0 °C");
}

void test_forecast_primary_press_returns_to_the_home_screen() {
  const DisplayModel model = reduce_status(healthy_status(), true, true);
  assert(primary_press(DisplayPage::Forecast, model) ==
         DisplayInteraction::ShowHome);
}

void test_home_primary_press_starts_the_timed_shower() {
  const DisplayModel model = reduce_status(healthy_status(), true, true);
  assert(primary_press(DisplayPage::Home, model) ==
         DisplayInteraction::TimedShower);
}

void test_active_shower_primary_press_drains_immediately() {
  HubStatus status = healthy_status();
  status.state = "TIMED_SHOWER";
  status.action = DisplayAction::CloseNow;
  const DisplayModel model = reduce_status(status, true, true);
  assert(primary_press(DisplayPage::Home, model) == DisplayInteraction::Drain);
}

void test_hub_result_constructs_with_connection_and_status() {
  HubStatus status{};
  status.state = "TIMED_SHOWER";
  HubResult result(true, status, 200);
  assert(result.connected);
  assert(result.status.state == "TIMED_SHOWER");
  assert(result.http_status == 200);
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
void test_sensor_visibility() { test_sensor_details_are_not_exposed_on_the_home_screen(); }
void test_forecast_press() { test_forecast_primary_press_returns_to_the_home_screen(); }
void test_start_shower() { test_home_primary_press_starts_the_timed_shower(); }
void test_stop_shower() { test_active_shower_primary_press_drains_immediately(); }
void test_hub_result() { test_hub_result_constructs_with_connection_and_status(); }
void test_action_paths() { test_action_paths_are_display_api_only(); }
void test_navigation() { test_encoder_navigation_has_exactly_two_pages(); }

void setup() {
  UNITY_BEGIN();
  RUN_TEST(test_offline);
  RUN_TEST(test_active_timer);
  RUN_TEST(test_sensor_visibility);
  RUN_TEST(test_forecast_press);
  RUN_TEST(test_start_shower);
  RUN_TEST(test_stop_shower);
  RUN_TEST(test_hub_result);
  RUN_TEST(test_action_paths);
  RUN_TEST(test_navigation);
  UNITY_END();
}

void loop() {}
#else
int main() {
  test_offline_disables_actions_and_shows_required_copy();
  test_active_timer_maps_primary_action_to_immediate_drain();
  test_sensor_details_are_not_exposed_on_the_home_screen();
  test_forecast_primary_press_returns_to_the_home_screen();
  test_home_primary_press_starts_the_timed_shower();
  test_active_shower_primary_press_drains_immediately();
  test_hub_result_constructs_with_connection_and_status();
  test_action_paths_are_display_api_only();
  test_encoder_navigation_has_exactly_two_pages();
}
#endif
