// Standalone LCD-only bench image. No secrets, Wi-Fi, Hub client or touch setup.
// The 28 and 28CT manufacturer classes share the LCD initialization/pin map.
#include <Arduino.h>
#include <gfx4desp32_gen4_ESP32_28.h>

namespace {
gfx4desp32_gen4_ESP32_28 panel;
void label(int x, int y, const char* value, int size = 1) {
  panel.TextSize(size);
  panel.TextColor(0xffff, 0x0000);
  panel.MoveTo(x, y);
  panel.print(value);
}
}
void setup() {
  Serial.begin(115200);
  Serial.println("GEN4_BENCH_BOOT v1");
  panel.begin();
  panel.Orientation(PORTRAIT);
  panel.Font(1);
  panel.BacklightOn(true);
  panel.Cls(0x0000);
  panel.Rectangle(0, 0, 239, 319, 0xffff);
  label(10, 10, "TL");
  label(216, 10, "TR");
  label(30, 35, "GEN4 2.8 TEST", 2);
  panel.RectangleFilled(12, 75, 83, 119, 0xf800);
  panel.RectangleFilled(84, 75, 155, 119, 0x07e0);
  panel.RectangleFilled(156, 75, 227, 119, 0x001f);
  label(12, 132, "RDECA  ZELENA  MODRA", 2);
  label(24, 177, "BREZ OMREZJA", 2);
  label(24, 205, "DOTIK NI VKLJUCEN");
  char memory[48];
  snprintf(memory, sizeof(memory), "Flash %u MB / PSRAM %u MB",
           unsigned(ESP.getFlashChipSize() / 1048576),
           unsigned(ESP.getPsramSize() / 1048576));
  label(24, 235, memory);
  label(10, 300, "BL");
  label(216, 300, "BR");
  Serial.printf("GEN4_BENCH_READY v1 width=240 height=320 flash=%u psram=%u\n",
                unsigned(ESP.getFlashChipSize()), unsigned(ESP.getPsramSize()));
}
void loop() {
  static uint32_t last = 0;
  const uint32_t now = millis();
  if (uint32_t(now - last) >= 2000) {
    last = now;
    char uptime[32];
    snprintf(uptime, sizeof(uptime), "Uptime %8lu s", static_cast<unsigned long>(now / 1000));
    label(24, 266, uptime);
    Serial.printf("GEN4_BENCH_ALIVE uptime_s=%lu\n", static_cast<unsigned long>(now / 1000));
  }
  delay(10);
}
