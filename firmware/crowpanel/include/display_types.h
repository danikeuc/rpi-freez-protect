#pragma once

#include <array>
#include <string>

enum class DisplayAction { None, TimedShower, CloseNow };
enum class DisplayPage { Home, Forecast };
enum class DisplayInteraction { None, ShowHome, TimedShower, Drain };

struct ForecastData {
  bool available = false;
  bool fresh = false;
  std::array<std::string, 7> dates{};
  std::array<float, 7> minima_c{};
  std::string fetched_at;
};

struct HubStatus {
  std::string state;
  std::string reason;
  bool has_pipe_temperature = false;
  float pipe_temperature_c = 0.0F;
  std::string sensor_health;
  ForecastData forecast;
  std::string timed_shower_deadline;
  DisplayAction action = DisplayAction::None;
  bool action_enabled = false;
};

struct DisplayModel {
  DisplayPage page = DisplayPage::Home;
  std::string state;
  std::string reason;
  std::string pipe_temperature_text;
  std::string sensor_health;
  ForecastData forecast;
  std::string forecast_text;
  std::string connection_text;
  std::string connection_detail_text;
  bool connected = false;
  std::string primary_action_text;
  std::string primary_action_detail;
  std::string forecast_summary_text;
  std::string timed_shower_deadline;
  DisplayAction action = DisplayAction::None;
  bool action_enabled = false;
};
