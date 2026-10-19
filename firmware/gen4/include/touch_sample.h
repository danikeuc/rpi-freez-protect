#pragma once
#include <cstddef>
#include <cstdint>

namespace gen4 {
enum class TouchState { kInvalid, kWaiting, kReleased, kPressed };
struct TouchSample {
  TouchState state = TouchState::kInvalid;
  int x = 0;
  int y = 0;
};
// Wire is injected so truncated reads and failed ACKs can be exercised on host.
// Portrait coordinates match the pinned manufacturer's gen4-ESP32-28CT driver.
template<class Bus> class TouchReader {
 public:
  explicit TouchReader(Bus& bus) : bus_(bus) {}
  TouchSample read(int controller, uint8_t address) {
    TouchSample sample;
    if (controller == 0 && address == 0x38) {
      uint8_t data[6] = {};
      if (!read_register(address, 2, false, data, sizeof(data))) return sample;
      if (data[0] == 0) sample.state = TouchState::kReleased;
      else if (data[0] == 1 && (data[1] >> 6) != 3) {
        sample.x = ((data[1] & 15) << 8) | data[2];
        sample.y = ((data[3] & 15) << 8) | data[4];
        // Event 1 is lift-up; never turn it into another pressed sample.
        sample.state = (data[1] >> 6) == 1 ? TouchState::kReleased : TouchState::kPressed;
      }
    } else if (controller == 1 && (address == 0x5d || address == 0x14)) {
      uint8_t status = 0;
      if (!read_register(address, 0x814e, true, &status, 1)) return sample;
      if (!(status & 0x80)) { sample.state = TouchState::kWaiting; return sample; }
      const unsigned count = status & 15;
      uint8_t point[8] = {};
      const bool complete = count != 1 ||
          read_register(address, 0x814f, true, point, sizeof(point));
      bus_.beginTransmission(address);
      bus_.write(uint8_t(0x81));
      bus_.write(uint8_t(0x4e));
      bus_.write(uint8_t(0));
      if (bus_.endTransmission() != 0 || !complete) return sample;
      if (count == 0) sample.state = TouchState::kReleased;
      else if (count == 1) {
        sample.x = point[1] | (point[2] << 8);
        sample.y = point[3] | (point[4] << 8);
        sample.state = TouchState::kPressed;
      }
    }
    if (sample.state == TouchState::kPressed &&
        (sample.x >= 240 || sample.y >= 320)) sample.state = TouchState::kInvalid;
    return sample;
  }
 private:
  Bus& bus_;
  bool read_register(uint8_t address, uint16_t reg, bool wide,
                     uint8_t* out, std::size_t size) {
    bus_.beginTransmission(address);
    if (wide) bus_.write(uint8_t(reg >> 8));
    bus_.write(uint8_t(reg));
    if (bus_.endTransmission(false) != 0) return false;
    if (bus_.requestFrom(address, size) != size) return false;
    for (std::size_t i = 0; i < size; ++i) {
      if (bus_.available() <= 0) return false;
      const int value = bus_.read();
      if (value < 0) return false;
      out[i] = uint8_t(value);
    }
    return true;
  }
};
}  // namespace gen4
