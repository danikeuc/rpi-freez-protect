#pragma once
#include <cstddef>
#include <cstdint>

namespace gen4 {
constexpr uint32_t kStaleMs = 5000;
constexpr uint32_t kHoldMs = 2000;
enum class Command { Unknown, Drain, Supply };
enum class Action { None, Start, Drain };
struct Status {
  Command command = Command::Unknown;
  bool manual = false;
  bool may_start = false;
  int remaining_seconds = 0;
};
bool parse_status(const char* json, std::size_t length, Status& out);
bool valid_receipt(const char* json, std::size_t length, Action action);
struct Model {
  Status status{};
  bool valid = false;
  bool pending = false;
  uint32_t received_ms = 0;
  uint32_t request_id = 0;
  uint32_t begin_request();
  bool accept(const Status& value, bool ok, uint32_t received, uint32_t completed_id);
  bool fresh(uint32_t now) const;
  bool can_start(uint32_t now) const;
  int remaining(uint32_t now) const;
};
// Require a release before the first gesture and after every fired/cancelled one.
// Moving between buttons, losing freshness or changing intent cancels the hold.
class Gesture {
 public:
  Action update(bool down, Action target, const Model& model, uint32_t now,
                bool sample_valid = true);
  bool holding_start(uint32_t now) const {
    return active_ && target_ == Action::Start && sampled_ &&
           uint32_t(now - sampled_ms_) <= 100;
  }
 private:
  bool sampled_ = false;
  uint32_t sampled_ms_ = 0;
  bool armed_ = false;
  bool active_ = false;
  Action target_ = Action::None;
  uint32_t started_ = 0;
};
inline bool should_render(bool changed, uint32_t now, uint32_t last_render,
                          const Gesture& gesture, const Model& model) {
  if (gesture.holding_start(now) && model.can_start(now)) return false;
  return changed || uint32_t(now - last_render) >= 1000;
}
}  // namespace gen4
