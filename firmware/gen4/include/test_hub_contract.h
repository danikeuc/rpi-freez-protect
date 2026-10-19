#pragma once
#include <cstddef>
#include <ArduinoJson.h>
namespace gen4 {
inline bool is_test_hub_response(const char* json, std::size_t length) {
  JsonDocument doc;
  if (deserializeJson(doc, json, length)) return false;
  return doc["simulated"].is<bool>() && doc["simulated"].as<bool>();
}
}
