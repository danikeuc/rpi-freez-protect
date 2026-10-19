// Isolated diagnostic: no secrets, Wi-Fi, Hub client or valve control.
// Shared 28 LCD driver; only the documented internal CTP I2C bus is probed.
#include <Arduino.h>
#include <Wire.h>
#include <gfx4desp32_gen4_ESP32_28.h>
#include "touch_sample.h"

namespace {
gfx4desp32_gen4_ESP32_28 panel;
gen4::TouchReader<TwoWire> reader(Wire);
// Pinned GFX4dESP32 gfx4desp32_spi_panel_t.cpp uses SDA=10, SCL=9.
constexpr int kSda = 10;
constexpr int kScl = 9;
constexpr uint8_t kAddresses[] = {0x38, 0x5d, 0x14};
bool bus_ready = false;
uint8_t mask = 0;
uint8_t address = 0;
int controller = -1;
// Read-only FT register snapshots: mode, chip/cipher, firmware, vendor, power.
constexpr uint8_t kIdRegisters[] = {0x00, 0xa3, 0xa6, 0xa8, 0xa5};
int before_id[5] = {-1, -1, -1, -1, -1};
int after_id[5] = {-1, -1, -1, -1, -1};
bool reset_done = false;
int ft_register(uint8_t reg) {
  Wire.beginTransmission(0x38);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0 ||
      Wire.requestFrom(uint8_t(0x38), size_t(1)) != 1 || Wire.available() != 1) return -1;
  return Wire.read();
}
void snapshot_id(int* values) {
  for (unsigned i = 0; i < 5; ++i) values[i] = ft_register(kIdRegisters[i]);
}
uint32_t pressed = 0, released = 0, invalid = 0, waiting = 0;
int last_x = 0, last_y = 0;
gen4::TouchState state = gen4::TouchState::kInvalid;

void label(int x, int y, const char* value, int size = 1) {
  panel.TextSize(size);
  panel.TextColor(0xffff, 0);
  panel.MoveTo(x, y);
  panel.print(value);
}
void render() {
  panel.Cls(0);
  panel.Rectangle(0, 0, 239, 319, 0xffff);
  label(24, 12, "GEN4 DOTIK V2", 2);
  label(24, 42, "BREZ OMREZJA");
  char line[48];
  snprintf(line, sizeof(line), "I2C mask=%u bus=%u", unsigned(mask), unsigned(bus_ready));
  label(18, 70, line);
  if (!bus_ready) label(18, 100, "NAPAKA VODILA");
  else if (controller < 0) label(18, 100, mask ? "ODZIV NI POTRJEN" : "NI ODZIVA NA I2C");
  else {
    snprintf(line, sizeof(line), "Naslov 0x%02X (kandidat)", unsigned(address));
    label(18, 100, line);
    label(18, 124, "Dotakni se vogalov in sredine.");
  }
  snprintf(line, sizeof(line), "x=%3d y=%3d", last_x, last_y);
  label(18, 156, line, 2);
  snprintf(line, sizeof(line), "P=%lu R=%lu E=%lu", (unsigned long)pressed,
           (unsigned long)released, (unsigned long)invalid);
  label(18, 188, line);
  label(18, 216, "P=dotik R=spust E=neveljavno");
  snprintf(line, sizeof(line), "Reset=%u ID=%d FW=%d", unsigned(reset_done), after_id[1], after_id[2]);
  label(18, 242, line);
  label(18, 260, "Brez odziva: vzrok se ni znan.");
  if (state == gen4::TouchState::kPressed) {
    const int x = constrain(last_x, 3, 236);
    const int y = constrain(last_y, 3, 316);
    panel.RectangleFilled(x - 3, y - 3, x + 3, y + 3, 0x07e0);
  }
}
void report() {
  Serial.printf("GEN4_TOUCH_PROBE v2 mask=%u bus=%u pressed=%lu released=%lu invalid=%lu waiting=%lu x=%d y=%d\n",
                unsigned(mask), unsigned(bus_ready), (unsigned long)pressed,
                (unsigned long)released, (unsigned long)invalid,
                (unsigned long)waiting, last_x, last_y);
  Serial.printf("GEN4_TOUCH_ID reset=%u before=%d,%d,%d,%d,%d after=%d,%d,%d,%d,%d\n",
                unsigned(reset_done), before_id[0], before_id[1], before_id[2], before_id[3], before_id[4],
                after_id[0], after_id[1], after_id[2], after_id[3], after_id[4]);
}
}
void setup() {
  Serial.begin(115200);
  panel.begin();
  panel.Orientation(PORTRAIT);
  panel.Font(1);
  panel.BacklightOn(true);
  // Probe first; apply the documented FT reset only for a unique 0x38 ACK.
  bus_ready = Wire.begin(kSda, kScl, 100000);
  Wire.setTimeOut(20);
  delay(100);
  if (bus_ready) {
    for (unsigned i = 0; i < 3; ++i) {
      Wire.beginTransmission(kAddresses[i]);
      if (Wire.endTransmission() == 0) mask |= uint8_t(1u << i);
    }
    // Address ACK is only a candidate. Ambiguous responses never select a reader.
    if (mask == 1) {
      snapshot_id(before_id);
      // Exact FT branch sequence from the pinned manufacturer's SPI touch driver.
      pinMode(GFX4d_TOUCH_INT, INPUT);
      pinMode(GFX4d_TOUCH_RESET, OUTPUT);
      digitalWrite(GFX4d_TOUCH_RESET, LOW);
      delay(100);
      digitalWrite(GFX4d_TOUCH_RESET, HIGH);
      delay(50);
      pinMode(GFX4d_TOUCH_INT, INPUT_PULLUP);
      reset_done = true;
      snapshot_id(after_id);
      bool complete = true;
      for (int value : after_id) if (value < 0) complete = false;
      if (complete) { address = 0x38; controller = 0; }
    }
    if (mask == 2) { address = 0x5d; controller = 1; }
    if (mask == 4) { address = 0x14; controller = 1; }
  }
  render();
  report();
}
void loop() {
  if (controller >= 0) {
    // Uses validated full frames. GT reads acknowledge the consumed ready frame;
    // this clears its status register, but does not configure controller firmware.
    const gen4::TouchSample sample = reader.read(controller, address);
    state = sample.state;
    switch (state) {
      case gen4::TouchState::kPressed:
        ++pressed; last_x = sample.x; last_y = sample.y; break;
      case gen4::TouchState::kReleased: ++released; break;
      case gen4::TouchState::kWaiting: ++waiting; break;
      default: ++invalid; break;
    }
  }
  static uint32_t last_render = 0, last_report = 0;
  const uint32_t now = millis();
  if (uint32_t(now - last_render) >= 200) { last_render = now; render(); }
  if (uint32_t(now - last_report) >= 2000) { last_report = now; report(); }
  delay(20);
}
