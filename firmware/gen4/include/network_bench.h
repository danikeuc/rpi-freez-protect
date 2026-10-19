#pragma once
#include <cstdint>
namespace gen4 {
// One-shot schedule only; production Wi-Fi/status handling remains unchanged.
// 0 idle, 1 deliberate outage, 2 recovery, 3 fresh status restored, 4 timeout.
class NetworkBench {
 public:
  bool begin(uint32_t now, bool connected, bool fresh) {
    if (phase_ != 0 || !connected || !fresh) return false;
    phase_ = 1;
    started_ = now;
    return true;
  }
  void disconnected(bool ok) { disconnect_ok_ = ok; }
  bool reconnect_due(uint32_t now, bool connected, bool fresh) {
    if (phase_ == 1 && !connected && !fresh) saw_loss_ = true;
    if (phase_ == 1 && uint32_t(now - started_) >= 30000) {
      phase_ = 2;
      started_ = now;
      return true;
    }
    if (phase_ == 2) {
      if (uint32_t(now - started_) >= 30000) phase_ = 4;
      else if (connected && fresh) phase_ = disconnect_ok_ && saw_loss_ ? 3 : 4;
    }
    return false;
  }
  unsigned phase() const { return phase_; }
 private:
  unsigned phase_ = 0;
  uint32_t started_ = 0;
  bool disconnect_ok_ = false;
  bool saw_loss_ = false;
};
}
