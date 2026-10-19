#include "model.h"
#include <ArduinoJson.h>
#include <algorithm>
#include <cstring>

namespace gen4 {
namespace {
bool equals(JsonVariantConst v, const char* text) {
  return v.is<const char*>() && std::strcmp(v.as<const char*>(), text) == 0;
}
}
bool parse_status(const char* json, std::size_t length, Status& out) {
  out = {};
  JsonDocument doc;
  if (deserializeJson(doc, json, length) || !doc.is<JsonObject>()) return false;
  if (!doc["state"].is<const char*>() || !doc["reason"].is<const char*>() ||
      !doc["action_enabled"].is<bool>() || !doc["remaining_seconds"].is<int>())
    return false;
  if (!equals(doc["mode"], "manual_timed") &&
      !equals(doc["mode"], "safe_drain") && !equals(doc["mode"], "automatic") &&
      !equals(doc["mode"], "weather_assisted"))
    return false;
  if (!equals(doc["action"], "TIMED_SHOWER") && !equals(doc["action"], "CLOSE_NOW"))
    return false;
  Status parsed;
  if (equals(doc["command"], "DRAIN")) parsed.command = Command::Drain;
  else if (equals(doc["command"], "SUPPLY")) parsed.command = Command::Supply;
  else return false;
  parsed.remaining_seconds = doc["remaining_seconds"].as<int>();
  parsed.manual = equals(doc["mode"], "manual_timed");
  // The Hub allows up to 30 minutes outside manual mode; manual showers
  // remain capped at 10 minutes.
  if (parsed.remaining_seconds < 0 ||
      parsed.remaining_seconds > (parsed.manual ? 600 : 1800)) return false;
  if (parsed.command == Command::Drain && parsed.remaining_seconds != 0) return false;
  parsed.may_start = parsed.manual && parsed.command == Command::Drain &&
      equals(doc["state"], "MANUAL_DRAIN") &&
      equals(doc["action"], "TIMED_SHOWER") && doc["action_enabled"].as<bool>();
  out = parsed;
  return true;
}
bool valid_receipt(const char* json, std::size_t length, Action action) {
  JsonDocument doc;
  if (deserializeJson(doc, json, length) || !doc.is<JsonObject>() ||
      !doc["state"].is<const char*>() || !doc["reason"].is<const char*>() ||
      equals(doc["state"], "FAULT")) return false;
  if (action == Action::Start)
    return equals(doc["command"], "SUPPLY") && equals(doc["state"], "TIMED_SHOWER");
  return action == Action::Drain && equals(doc["command"], "DRAIN");
}
uint32_t Model::begin_request() {
  ++request_id;
  pending = true;
  valid = false;
  return request_id;
}
bool Model::accept(const Status& value, bool ok, uint32_t received, uint32_t completed_id) {
  if (pending && completed_id != request_id) return false;
  status = value;
  valid = ok;
  received_ms = received;
  pending = false;
  return true;
}
bool Model::fresh(uint32_t now) const {
  return valid && !pending && uint32_t(now - received_ms) < kStaleMs;
}
bool Model::can_start(uint32_t now) const {
  return fresh(now) && status.may_start;
}
int Model::remaining(uint32_t now) const {
  if (!fresh(now)) return -1;
  return std::max(0, status.remaining_seconds - int(uint32_t(now - received_ms) / 1000));
}
Action Gesture::update(bool down, Action target, const Model& model, uint32_t now,
                       bool sample_valid) {
  if (!sample_valid || (sampled_ && uint32_t(now - sampled_ms_) > 100)) {
    armed_ = false;
    active_ = false;
  }
  sampled_ = true;
  sampled_ms_ = now;
  // An unreadable sensor is not evidence of release.
  if (!sample_valid) return Action::None;
  if (!down) {
    armed_ = true;
    active_ = false;
    target_ = Action::None;
    return Action::None;
  }
  const bool allowed = model.fresh(now) &&
      (target == Action::Drain || (target == Action::Start && model.can_start(now)));
  if (!armed_ || !allowed || (active_ && target != target_)) {
    armed_ = false;
    active_ = false;
    return Action::None;
  }
  if (!active_) {
    active_ = true;
    target_ = target;
    started_ = now;
  }
  if (target == Action::Drain || uint32_t(now - started_) >= kHoldMs) {
    armed_ = false;
    active_ = false;
    return target;
  }
  return Action::None;
}
}  // namespace gen4
