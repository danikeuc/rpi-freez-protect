#include <cassert>
#include <string>

#include "display_state.h"
#include "display_layout.h"
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

void test_connection_diagnostic_distinguishes_wifi_and_hub_failures() {
  assert(connection_diagnostic(false, false, 0, 0) ==
         "WI-FI: POVEZOVANJE");
  assert(connection_diagnostic(false, false, 0, 1) ==
         "WI-FI: SSID NI NAJDEN");
  assert(connection_diagnostic(false, false, 0, 4) ==
         "WI-FI: PRIJAVA NI USPELA");
  assert(connection_diagnostic(false, false, 0, 5) ==
         "WI-FI: POVEZAVA IZGUBLJENA");
  assert(connection_diagnostic(false, false, 0, 6) ==
         "WI-FI: ODKLOPLJEN");
  assert(connection_diagnostic(true, false, 0, 3) == "HUB NEDOSEGLJIV");
  assert(connection_diagnostic(true, false, 401, 3) == "HUB HTTP 401");
  assert(connection_diagnostic(true, false, 200, 3) == "HUB ODGOVOR NAPAKA");
  assert(connection_diagnostic(true, true, 200, 3) == "HUB POVEZAN");
}

void test_wifi_diagnostic_exposes_device_state_and_network_identity() {
  assert(wifi_diagnostic_details(6, "192.168.114.226", "AA:BB:CC:92:AE:DC",
                                201, 200, true, 0, true) ==
         "Wi-Fi status: 6\nIP: 192.168.114.226\nMAC: AA:BB:CC:92:AE:DC\n"
         "Disconnect reason: 201\nHub HTTP: 200, JSON valid (0s ago)");
  assert(wifi_diagnostic_details(0, "0.0.0.0", "AA:BB:CC:92:AE:DC", -1,
                                0, false, 0, false) ==
         "Wi-Fi status: 0\nIP: 0.0.0.0\nMAC: AA:BB:CC:92:AE:DC\n"
         "Disconnect reason: none\nHub: no poll yet");
  assert(wifi_diagnostic_details(6, "0.0.0.0", "AA:BB:CC:92:AE:DC", 201,
                                200, false, 5, true) ==
         "Wi-Fi status: 6\nIP: 0.0.0.0\nMAC: AA:BB:CC:92:AE:DC\n"
         "Disconnect reason: 201\nHub HTTP: 200, JSON invalid (5s ago)");
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
  assert(std::string(HubClient::kDrainPath) ==
         "/api/v1/display/actions/drain");
}

void test_encoder_navigation_has_exactly_two_pages() {
  assert(move_page(DisplayPage::Home, true) == DisplayPage::Forecast);
  assert(move_page(DisplayPage::Forecast, false) == DisplayPage::Home);
}

void test_home_state_label_reflects_hub_state() {
  HubStatus status = healthy_status();
  status.state = "NORMAL";
  assert(home_state_label(reduce_status(status, true, true)) ==
         "NORMALNO DELOVANJE");

  status.state = "FROST_PROTECTION";
  assert(home_state_label(reduce_status(status, true, true)) ==
         "ZAŠČITA PRED MRAZOM");

  status.state = "FAULT";
  assert(home_state_label(reduce_status(status, true, true)) ==
         "NAPAKA SISTEMA");

  status.state = "TIMED_SHOWER";
  assert(home_state_label(reduce_status(status, true, true)) == "TUŠ AKTIVEN");

  assert(home_state_label(reduce_status(status, true, false)) == "NI POVEZAVE");
}

void test_forecast_rows_fit_above_the_return_prompt() {
  constexpr int rows_bottom = DisplayLayout::kForecastRowsY +
                              DisplayLayout::kForecastLineCount *
                                  DisplayLayout::kForecastLineHeight;
  constexpr int footer_top = DisplayLayout::kDisplayHeight -
                             DisplayLayout::kForecastFooterBottomMargin -
                             DisplayLayout::kForecastFooterFontHeight;
  assert(rows_bottom <= footer_top);
}

}  // namespace

#ifdef PIO_UNIT_TESTING
#include <unity.h>

extern "C" void setUp(void) {}
extern "C" void tearDown(void) {}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_offline_disables_actions_and_shows_required_copy);
  RUN_TEST(test_connection_diagnostic_distinguishes_wifi_and_hub_failures);
  RUN_TEST(test_wifi_diagnostic_exposes_device_state_and_network_identity);
  RUN_TEST(test_active_timer_maps_primary_action_to_immediate_drain);
  RUN_TEST(test_sensor_details_are_not_exposed_on_the_home_screen);
  RUN_TEST(test_forecast_primary_press_returns_to_the_home_screen);
  RUN_TEST(test_home_primary_press_starts_the_timed_shower);
  RUN_TEST(test_active_shower_primary_press_drains_immediately);
  RUN_TEST(test_hub_result_constructs_with_connection_and_status);
  RUN_TEST(test_action_paths_are_display_api_only);
  RUN_TEST(test_encoder_navigation_has_exactly_two_pages);
  RUN_TEST(test_home_state_label_reflects_hub_state);
  RUN_TEST(test_forecast_rows_fit_above_the_return_prompt);
  return UNITY_END();
}
#else
int main() {
  test_offline_disables_actions_and_shows_required_copy();
  test_connection_diagnostic_distinguishes_wifi_and_hub_failures();
  test_wifi_diagnostic_exposes_device_state_and_network_identity();
  test_active_timer_maps_primary_action_to_immediate_drain();
  test_sensor_details_are_not_exposed_on_the_home_screen();
  test_forecast_primary_press_returns_to_the_home_screen();
  test_home_primary_press_starts_the_timed_shower();
  test_active_shower_primary_press_drains_immediately();
  test_hub_result_constructs_with_connection_and_status();
  test_action_paths_are_display_api_only();
  test_encoder_navigation_has_exactly_two_pages();
  test_home_state_label_reflects_hub_state();
  test_forecast_rows_fit_above_the_return_prompt();
}
#endif
