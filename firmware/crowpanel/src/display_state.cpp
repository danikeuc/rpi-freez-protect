#include "display_state.h"

#include <cstdio>

namespace {

std::string format_temperature(float value_c) {
  char buffer[20]{};
  std::snprintf(buffer, sizeof(buffer), "%.1f °C", static_cast<double>(value_c));
  return buffer;
}

}  // namespace

DisplayModel reduce_status(const HubStatus& status, bool wifi_connected,
                           bool hub_connected) {
  DisplayModel model{};
  model.state = status.state;
  model.reason = status.reason;
  model.sensor_health = status.sensor_health;
  model.forecast = status.forecast;
  model.timed_shower_deadline = status.timed_shower_deadline;
  model.pipe_temperature_text = status.has_pipe_temperature
                                    ? format_temperature(status.pipe_temperature_c)
                                    : "SENZOR ČAKA";
  model.forecast_text = status.forecast.available && status.forecast.fresh
                            ? "NAPOVED OSVEŽENA"
                            : "NAPOVED NI NA VOLJO";

  if (!wifi_connected || !hub_connected) {
    model.connection_text = "NI POVEZAVE — PREVERI HUB";
    model.primary_action_text = "NI NA VOLJO";
    model.action = DisplayAction::None;
    model.action_enabled = false;
    return model;
  }

  model.connection_text = "HUB POVEZAN";
  model.action = status.action;
  model.action_enabled = status.action_enabled && status.action != DisplayAction::None;
  model.primary_action_text = status.action == DisplayAction::CloseNow
                                  ? "ZAPRI TAKOJ"
                                  : "TUŠ 10 MIN";
  return model;
}

DisplayAction next_action(const DisplayModel& model) {
  return model.action_enabled ? model.action : DisplayAction::None;
}

DisplayPage move_page(DisplayPage current, bool forward) {
  if (current == DisplayPage::Home && forward) {
    return DisplayPage::Forecast;
  }
  if (current == DisplayPage::Forecast && !forward) {
    return DisplayPage::Home;
  }
  return current;
}
