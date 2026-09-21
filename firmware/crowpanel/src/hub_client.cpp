#include "hub_client.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>

#include <utility>

namespace {

bool read_string(JsonVariantConst value, std::string& destination) {
  if (!value.is<const char*>()) {
    return false;
  }
  destination = value.as<const char*>();
  return true;
}

DisplayAction parse_action(const char* value) {
  if (value == nullptr) {
    return DisplayAction::None;
  }
  if (std::string(value) == "TIMED_SHOWER") {
    return DisplayAction::TimedShower;
  }
  if (std::string(value) == "CLOSE_NOW") {
    return DisplayAction::CloseNow;
  }
  return DisplayAction::None;
}

bool parse_status(const String& payload, HubStatus& status) {
  JsonDocument document;
  if (deserializeJson(document, payload) != DeserializationError::Ok) {
    return false;
  }
  const JsonObjectConst root = document.as<JsonObjectConst>();
  if (root.isNull() || !read_string(root["state"], status.state) ||
      !read_string(root["reason"], status.reason)) {
    return false;
  }
  if (root["pipe_temperature_c"].is<float>() ||
      root["pipe_temperature_c"].is<double>() ||
      root["pipe_temperature_c"].is<int>()) {
    status.has_pipe_temperature = true;
    status.pipe_temperature_c = root["pipe_temperature_c"].as<float>();
  }
  if (!root["sensor_health"].isNull()) {
    read_string(root["sensor_health"], status.sensor_health);
  }
  if (!root["timed_shower_deadline"].isNull()) {
    read_string(root["timed_shower_deadline"], status.timed_shower_deadline);
  }
  const JsonObjectConst forecast = root["forecast"].as<JsonObjectConst>();
  if (forecast.isNull() || !forecast["available"].is<bool>() ||
      !forecast["fresh"].is<bool>()) {
    return false;
  }
  status.forecast.available = forecast["available"].as<bool>();
  status.forecast.fresh = forecast["fresh"].as<bool>();
  if (!forecast["fetched_at"].isNull()) {
    read_string(forecast["fetched_at"], status.forecast.fetched_at);
  }
  const JsonArrayConst dates = forecast["dates"].as<JsonArrayConst>();
  const JsonArrayConst minima = forecast["minima_c"].as<JsonArrayConst>();
  if ((status.forecast.available || status.forecast.fresh) &&
      (dates.size() != 7 || minima.size() != 7)) {
    return false;
  }
  for (std::size_t index = 0; index < dates.size() && index < 7; ++index) {
    if (!read_string(dates[index], status.forecast.dates[index]) ||
        !(minima[index].is<float>() || minima[index].is<double>() ||
          minima[index].is<int>())) {
      return false;
    }
    status.forecast.minima_c[index] = minima[index].as<float>();
  }
  if (!root["action"].is<const char*>() || !root["action_enabled"].is<bool>()) {
    return false;
  }
  status.action = parse_action(root["action"].as<const char*>());
  status.action_enabled = root["action_enabled"].as<bool>();
  return status.action != DisplayAction::None;
}

}  // namespace

HubClient::HubClient(std::string base_url, std::string display_token)
    : base_url_(std::move(base_url)), display_token_(std::move(display_token)) {
  while (!base_url_.empty() && base_url_.back() == '/') {
    base_url_.pop_back();
  }
}

HubResult HubClient::poll() {
  HTTPClient http;
  http.setConnectTimeout(5000);
  http.setTimeout(5000);
  if (!http.begin(endpoint(kStatusPath).c_str())) {
    return {};
  }
  http.addHeader("X-Display-Token", display_token_.c_str());
  http.addHeader("Accept", "application/json");
  const int response_code = http.GET();
  if (response_code != HTTP_CODE_OK) {
    http.end();
    return {};
  }
  HubStatus status{};
  const bool valid = parse_status(http.getString(), status);
  http.end();
  return HubResult(valid, status);
}

bool HubClient::start_timed_shower() { return post(kTimedShowerPath); }

bool HubClient::drain() { return post(kDrainPath); }

std::string HubClient::endpoint(const char* path) const {
  return base_url_ + path;
}

bool HubClient::post(const char* path) {
  HTTPClient http;
  http.setConnectTimeout(5000);
  http.setTimeout(5000);
  if (!http.begin(endpoint(path).c_str())) {
    return false;
  }
  http.addHeader("X-Display-Token", display_token_.c_str());
  http.addHeader("Accept", "application/json");
  const int response_code = http.POST("");
  http.end();
  return response_code == HTTP_CODE_OK;
}
