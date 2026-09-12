#define LGFX_USE_V1

#include "hardware.h"

#include <Arduino.h>
#include <LovyanGFX.hpp>
#include <Wire.h>
#include <lvgl.h>

#include <array>
#include <cstdio>
#include <string>

#include "board_pins.h"

namespace {

class CrowPanelDisplay : public lgfx::LGFX_Device {
 public:
  CrowPanelDisplay() {
    auto bus_config = bus_.config();
    bus_config.spi_host = SPI2_HOST;
    bus_config.spi_mode = 0;
    bus_config.freq_write = 80000000;
    bus_config.freq_read = 20000000;
    bus_config.spi_3wire = true;
    bus_config.use_lock = true;
    bus_config.dma_channel = SPI_DMA_CH_AUTO;
    bus_config.pin_sclk = BoardPins::kDisplaySclk;
    bus_config.pin_mosi = BoardPins::kDisplayMosi;
    bus_config.pin_miso = -1;
    bus_config.pin_dc = BoardPins::kDisplayDc;
    bus_.config(bus_config);
    panel_.setBus(&bus_);

    auto panel_config = panel_.config();
    panel_config.pin_cs = BoardPins::kDisplayCs;
    panel_config.pin_rst = BoardPins::kDisplayReset;
    panel_config.pin_busy = -1;
    panel_config.memory_width = BoardPins::kDisplayWidth;
    panel_config.memory_height = BoardPins::kDisplayHeight;
    panel_config.panel_width = BoardPins::kDisplayWidth;
    panel_config.panel_height = BoardPins::kDisplayHeight;
    panel_config.offset_x = 0;
    panel_config.offset_y = 0;
    panel_config.offset_rotation = 0;
    panel_config.dummy_read_pixel = 8;
    panel_config.dummy_read_bits = 1;
    panel_config.readable = false;
    panel_config.invert = true;
    panel_config.rgb_order = false;
    panel_config.dlen_16bit = false;
    panel_config.bus_shared = false;
    panel_.config(panel_config);
    setPanel(&panel_);
  }

 private:
  lgfx::Panel_GC9A01 panel_;
  lgfx::Bus_SPI bus_;
};

CrowPanelDisplay display;
std::array<lv_color_t, BoardPins::kDisplayWidth * 20> draw_buffer{};
lv_disp_draw_buf_t lv_draw_buffer;
lv_obj_t* state_label = nullptr;
lv_obj_t* temperature_label = nullptr;
lv_obj_t* detail_label = nullptr;
lv_obj_t* action_label = nullptr;
int last_encoder_a = HIGH;
int last_button = HIGH;
bool touch_was_down = false;
unsigned long last_input_ms = 0;

void flush_display(lv_disp_drv_t* driver, const lv_area_t* area,
                   lv_color_t* colors) {
  const std::int32_t width = area->x2 - area->x1 + 1;
  const std::int32_t height = area->y2 - area->y1 + 1;
  display.startWrite();
  display.setAddrWindow(area->x1, area->y1, width, height);
  display.pushPixels(reinterpret_cast<std::uint16_t*>(&colors->full),
                     static_cast<std::size_t>(width * height), true);
  display.endWrite();
  lv_disp_flush_ready(driver);
}

std::string forecast_lines(const DisplayModel& model) {
  if (model.page == DisplayPage::Home) {
    return model.forecast_text + "\n" + model.connection_text + "\n" +
           model.reason;
  }
  if (!model.forecast.available) {
    return "NAPOVED NI NA VOLJO\n" + model.reason;
  }
  std::string lines = "MINIMALNE TEMPERATURE\n";
  for (std::size_t index = 0; index < model.forecast.dates.size(); ++index) {
    char row[40]{};
    std::snprintf(row, sizeof(row), "%s  %.1f C\n",
                  model.forecast.dates[index].c_str(),
                  static_cast<double>(model.forecast.minima_c[index]));
    lines += row;
  }
  if (!model.forecast.fetched_at.empty()) {
    lines += "POSODOBLJENO " + model.forecast.fetched_at.substr(0, 16) + "\n";
  }
  return lines + "\n" + model.reason;
}

bool touch_in_primary_area() {
  Wire.beginTransmission(0x15);
  Wire.write(0x02);
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom(0x15, 5) != 5) {
    return false;
  }
  const int fingers = Wire.read();
  const int x_high = Wire.read();
  const int x_low = Wire.read();
  const int y_high = Wire.read();
  const int y_low = Wire.read();
  const int y = ((y_high & 0x0F) << 8) | y_low;
  (void)x_high;
  (void)x_low;
  return fingers > 0 && y >= 175;
}

}  // namespace

void HardwareUi::begin() {
  pinMode(BoardPins::kPowerEnableOne, OUTPUT);
  pinMode(BoardPins::kPowerEnableTwo, OUTPUT);
  digitalWrite(BoardPins::kPowerEnableOne, HIGH);
  digitalWrite(BoardPins::kPowerEnableTwo, HIGH);
  pinMode(BoardPins::kEncoderA, INPUT_PULLUP);
  pinMode(BoardPins::kEncoderB, INPUT_PULLUP);
  pinMode(BoardPins::kEncoderButton, INPUT_PULLUP);
  last_encoder_a = digitalRead(BoardPins::kEncoderA);
  last_button = digitalRead(BoardPins::kEncoderButton);

  Wire.begin(BoardPins::kTouchSda, BoardPins::kTouchScl);
  pinMode(BoardPins::kTouchReset, OUTPUT);
  digitalWrite(BoardPins::kTouchReset, LOW);
  delay(5);
  digitalWrite(BoardPins::kTouchReset, HIGH);

  display.init();
  display.setRotation(0);
  ledcSetup(0, 5000, 8);
  ledcAttachPin(BoardPins::kBacklight, 0);
  ledcWrite(0, 255);

  lv_init();
  lv_disp_draw_buf_init(&lv_draw_buffer, draw_buffer.data(), nullptr,
                        draw_buffer.size());
  static lv_disp_drv_t display_driver;
  lv_disp_drv_init(&display_driver);
  display_driver.hor_res = BoardPins::kDisplayWidth;
  display_driver.ver_res = BoardPins::kDisplayHeight;
  display_driver.flush_cb = flush_display;
  display_driver.draw_buf = &lv_draw_buffer;
  lv_disp_drv_register(&display_driver);

  lv_obj_t* screen = lv_scr_act();
  lv_obj_set_style_bg_color(screen, lv_color_black(), 0);
  state_label = lv_label_create(screen);
  lv_obj_set_width(state_label, 210);
  lv_obj_align(state_label, LV_ALIGN_TOP_MID, 0, 16);
  lv_obj_set_style_text_align(state_label, LV_TEXT_ALIGN_CENTER, 0);
  temperature_label = lv_label_create(screen);
  lv_obj_set_width(temperature_label, 220);
  lv_obj_align(temperature_label, LV_ALIGN_TOP_MID, 0, 52);
  lv_obj_set_style_text_align(temperature_label, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_style_text_font(temperature_label, &lv_font_montserrat_20, 0);
  detail_label = lv_label_create(screen);
  lv_obj_set_width(detail_label, 210);
  lv_obj_align(detail_label, LV_ALIGN_TOP_MID, 0, 92);
  lv_obj_set_style_text_align(detail_label, LV_TEXT_ALIGN_CENTER, 0);
  action_label = lv_label_create(screen);
  lv_obj_set_width(action_label, 210);
  lv_obj_align(action_label, LV_ALIGN_BOTTOM_MID, 0, -20);
  lv_obj_set_style_text_align(action_label, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_style_text_font(action_label, &lv_font_montserrat_16, 0);
}

void HardwareUi::render(const DisplayModel& model) {
  lv_label_set_text(state_label, model.state.c_str());
  lv_label_set_text(temperature_label, model.pipe_temperature_text.c_str());
  const std::string detail = forecast_lines(model);
  lv_label_set_text(detail_label, detail.c_str());
  lv_label_set_text(action_label, model.primary_action_text.c_str());
  lv_obj_set_style_text_color(
      action_label,
      model.action_enabled ? lv_palette_main(LV_PALETTE_GREEN)
                           : lv_palette_main(LV_PALETTE_GREY),
      0);
}

InputEvent HardwareUi::poll_input() {
  const unsigned long now = millis();
  const int encoder_a = digitalRead(BoardPins::kEncoderA);
  if (encoder_a != last_encoder_a && encoder_a == HIGH &&
      now - last_input_ms > 40) {
    last_encoder_a = encoder_a;
    last_input_ms = now;
    return digitalRead(BoardPins::kEncoderB) != encoder_a
               ? InputEvent::NextPage
               : InputEvent::PreviousPage;
  }
  last_encoder_a = encoder_a;

  const int button = digitalRead(BoardPins::kEncoderButton);
  if (button == LOW && last_button == HIGH && now - last_input_ms > 200) {
    last_button = button;
    last_input_ms = now;
    return InputEvent::PrimaryAction;
  }
  last_button = button;

  const bool touch_down = touch_in_primary_area();
  if (touch_down && !touch_was_down && now - last_input_ms > 200) {
    touch_was_down = true;
    last_input_ms = now;
    return InputEvent::PrimaryAction;
  }
  touch_was_down = touch_down;
  return InputEvent::None;
}

void HardwareUi::tick() { lv_timer_handler(); }
