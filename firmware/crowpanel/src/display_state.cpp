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

std::string connection_diagnostic(bool wifi_connected, bool hub_connected,
                                  int http_status, int wifi_status) {
  if (!wifi_connected) {
    if (wifi_status == 0) {
      return "WI-FI: POVEZOVANJE";
    }
    if (wifi_status == 1) {
      return "WI-FI: SSID NI NAJDEN";
    }
    if (wifi_status == 4) {
      return "WI-FI: PRIJAVA NI USPELA";
    }
    if (wifi_status == 5) {
      return "WI-FI: POVEZAVA IZGUBLJENA";
    }
    if (wifi_status == 6) {
      return "WI-FI: ODKLOPLJEN";
    }
    return "WI-FI: NI POVEZAVE";
  }
  if (hub_connected) {
    return "HUB POVEZAN";
  }
  if (http_status == 200) {
    return "HUB ODGOVOR NAPAKA";
  }
  if (http_status > 0) {
    return "HUB HTTP " + std::to_string(http_status);
  }
  return "HUB NEDOSEGLJIV";
}

std::string wifi_diagnostic_details(int wifi_status, const std::string& ip,
                                    const std::string& mac,
                                    int disconnect_reason, int http_status,
                                    bool last_payload_valid,
                                    unsigned long last_poll_age_s,
                                    bool has_last_poll) {
  std::string details = "Wi-Fi status: " + std::to_string(wifi_status) +
                        "\nIP: " + ip + "\nMAC: " + mac +
                        "\nDisconnect reason: " +
                        (disconnect_reason < 0 ? "none"
                                               : std::to_string(disconnect_reason));
  if (!has_last_poll) {
    details += "\nHub: no poll yet";
  } else {
    details += "\nHub HTTP: " + std::to_string(http_status);
    if (http_status == 200) {
      details += last_payload_valid ? ", JSON valid" : ", JSON invalid";
    } else {
      details += ", no valid JSON";
    }
    details += " (" + std::to_string(last_poll_age_s) + "s ago)";
  }
  return details;
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

std::string home_state_label(const DisplayModel& model) {
  if (!model.connected) {
    return "NI POVEZAVE";
  }
  if (model.state == "TIMED_SHOWER") {
    return "TUŠ AKTIVEN";
  }
  if (model.state == "NORMAL") {
    return "NORMALNO DELOVANJE";
  }
  if (model.state == "FROST_PROTECTION") {
    return "ZAŠČITA PRED MRAZOM";
  }
  if (model.state == "FAULT") {
    return "NAPAKA SISTEMA";
  }
  if (model.state == "STARTING") {
    return "ZAGON SISTEMA";
  }
  return "STANJE NEZNANO";
}
