#include "display_state.h"

#include <algorithm>
#include <cstdio>

namespace {

std::string format_temperature(float value_c) {
  char buffer[20]{};
  std::snprintf(buffer, sizeof(buffer), "%.1f °C", static_cast<double>(value_c));
  for (char* character = buffer; *character != '\0'; ++character) {
    if (*character == '.') {
      *character = ',';
    }
  }
  return buffer;
}

std::string forecast_summary(const ForecastData& forecast) {
  if (!forecast.available || !forecast.fresh) {
    return "7 DNI · NAPOVED NI NA VOLJO";
  }
  const float minimum = *std::min_element(forecast.minima_c.begin(),
                                          forecast.minima_c.end());
  return "7 DNI · MIN " + format_temperature(minimum);
}

}  // namespace

DisplayModel reduce_status(const HubStatus& status, bool wifi_connected,
                           bool hub_connected) {
  DisplayModel model{};
  model.state = status.state;
  model.reason = status.reason;
  model.forecast = status.forecast;
  model.timed_shower_deadline = status.timed_shower_deadline;
  model.forecast_summary_text = forecast_summary(status.forecast);
  model.forecast_text = status.forecast.available && status.forecast.fresh
                            ? "NAPOVED OSVEŽENA"
                            : "NAPOVED NI NA VOLJO";

  if (!wifi_connected || !hub_connected) {
    model.connection_text = "NI POVEZAVE — PREVERI HUB";
    model.primary_action_text = "NI NA VOLJO";
    model.primary_action_detail.clear();
    model.action = DisplayAction::None;
    model.action_enabled = false;
    return model;
  }

  model.connected = true;
  model.connection_text = "HUB POVEZAN";
  model.action = status.action;
  model.action_enabled = status.action_enabled && status.action != DisplayAction::None;
  model.primary_action_text = status.action == DisplayAction::CloseNow
                                  ? "ZAPRI VODO"
                                  : "VKLOPI TUŠ";
  model.primary_action_detail = status.action == DisplayAction::TimedShower
                                    ? "10 MIN"
                                    : "";
  return model;
}

DisplayAction next_action(const DisplayModel& model) {
  return model.action_enabled ? model.action : DisplayAction::None;
}

DisplayInteraction primary_press(DisplayPage page, const DisplayModel& model) {
  if (page == DisplayPage::Forecast) {
    return DisplayInteraction::ShowHome;
  }
  if (!model.action_enabled) {
    return DisplayInteraction::None;
  }
  if (model.action == DisplayAction::TimedShower) {
    return DisplayInteraction::TimedShower;
  }
  if (model.action == DisplayAction::CloseNow) {
    return DisplayInteraction::Drain;
  }
  return DisplayInteraction::None;
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
