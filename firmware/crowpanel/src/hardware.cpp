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
lv_obj_t* action_detail_label = nullptr;
lv_obj_t* action_icon = nullptr;
int last_encoder_a = HIGH;
bool touch_was_down = false;
unsigned long last_input_ms = 0;
DialButton dial_button;

// Embedded 32x32 1-bit alpha icons. Keeping them in firmware avoids any
// dependency on Unicode/emoji glyphs installed on the display.
constexpr std::uint8_t kShowerIconPixels[] = {
    0x00, 0x00, 0x00, 0x00, 0x03, 0xE0, 0x00, 0x00,
    0x0C, 0x18, 0x00, 0x00, 0x10, 0x04, 0x00, 0x00,
    0x20, 0x02, 0x00, 0x00, 0x20, 0x02, 0x00, 0x00,
    0x20, 0x02, 0x00, 0x00, 0x10, 0x04, 0x00, 0x00,
    0x0C, 0x18, 0x00, 0x00, 0x03, 0xE0, 0x00, 0x00,
    0x00, 0x7F, 0x00, 0x00, 0x00, 0x3F, 0x80, 0x00,
    0x00, 0x1F, 0xC0, 0x00, 0x00, 0x0F, 0xE0, 0x00,
    0x00, 0x07, 0xF0, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x80, 0x00, 0x00, 0x00, 0x80, 0x00,
    0x00, 0x00, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x40, 0x00, 0x00, 0x00, 0x40, 0x00,
    0x00, 0x00, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x20, 0x00, 0x00, 0x00, 0x20, 0x00,
    0x00, 0x00, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};

constexpr std::uint8_t kStopIconPixels[] = {
    0x80, 0x00, 0x00, 0x01, 0x40, 0x00, 0x00, 0x02,
    0x20, 0x00, 0x00, 0x04, 0x10, 0x00, 0x00, 0x08,
    0x08, 0x00, 0x00, 0x10, 0x04, 0x00, 0x00, 0x20,
    0x02, 0x00, 0x00, 0x40, 0x01, 0x00, 0x00, 0x80,
    0x00, 0x80, 0x01, 0x00, 0x00, 0x40, 0x02, 0x00,
    0x00, 0x20, 0x04, 0x00, 0x00, 0x10, 0x08, 0x00,
    0x00, 0x08, 0x10, 0x00, 0x00, 0x04, 0x20, 0x00,
    0x00, 0x02, 0x40, 0x00, 0x00, 0x01, 0x80, 0x00,
    0x00, 0x00, 0xC0, 0x00, 0x00, 0x01, 0x80, 0x00,
    0x00, 0x02, 0x40, 0x00, 0x00, 0x04, 0x20, 0x00,
    0x00, 0x08, 0x10, 0x00, 0x00, 0x10, 0x08, 0x00,
    0x00, 0x20, 0x04, 0x00, 0x00, 0x40, 0x02, 0x00,
    0x00, 0x80, 0x01, 0x00, 0x01, 0x00, 0x00, 0x80,
    0x02, 0x00, 0x00, 0x40, 0x04, 0x00, 0x00, 0x20,
    0x08, 0x00, 0x00, 0x10, 0x10, 0x00, 0x00, 0x08,
};

constexpr lv_img_dsc_t kShowerIcon = {
    {LV_IMG_CF_ALPHA_1BIT, 0, 0, 32, 32}, sizeof(kShowerIconPixels),
    kShowerIconPixels};
constexpr lv_img_dsc_t kStopIcon = {
    {LV_IMG_CF_ALPHA_1BIT, 0, 0, 32, 32}, sizeof(kStopIconPixels),
    kStopIconPixels};

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
  if (!model.forecast.available) {
    return "NAPOVED NI NA VOLJO";
  }
  std::string lines = "MINIMALNE TEMPERATURE\n";
  for (std::size_t index = 0; index < model.forecast.dates.size(); ++index) {
    char row[40]{};
    std::snprintf(row, sizeof(row), "%s  %.1f °C\n",
                  model.forecast.dates[index].substr(5).c_str(),
                  static_cast<double>(model.forecast.minima_c[index]));
    for (char* character = row; *character != '\0'; ++character) {
      if (*character == '.') {
        *character = ',';
      }
    }
    lines += row;
  }
  return lines;
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
  lv_obj_align(temperature_label, LV_ALIGN_TOP_MID, 0, 48);
  lv_obj_set_style_text_align(temperature_label, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_style_text_font(temperature_label, &lv_font_montserrat_20, 0);
  detail_label = lv_label_create(screen);
  lv_obj_set_width(detail_label, 210);
  lv_obj_align(detail_label, LV_ALIGN_TOP_MID, 0, 76);
  lv_obj_set_style_text_align(detail_label, LV_TEXT_ALIGN_CENTER, 0);
  action_label = lv_label_create(screen);
  lv_obj_set_width(action_label, 210);
  lv_obj_align(action_label, LV_ALIGN_BOTTOM_MID, 0, -26);
  lv_obj_set_style_text_align(action_label, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_style_text_font(action_label, &lv_font_montserrat_16, 0);
  action_detail_label = lv_label_create(screen);
  lv_obj_set_width(action_detail_label, 210);
  lv_obj_align(action_detail_label, LV_ALIGN_BOTTOM_MID, 0, -8);
  lv_obj_set_style_text_align(action_detail_label, LV_TEXT_ALIGN_CENTER, 0);
  action_icon = lv_img_create(screen);
  lv_obj_align(action_icon, LV_ALIGN_BOTTOM_MID, 0, -62);
}

void HardwareUi::render(const DisplayModel& model) {
  if (model.page == DisplayPage::Forecast) {
    lv_label_set_text(state_label, "7-DNEVNA NAPOVED");
    lv_label_set_text(temperature_label, "VRTI ZA PREKLOP");
    const std::string detail = forecast_lines(model);
    lv_label_set_text(detail_label, detail.c_str());
    lv_label_set_text(action_label, "PRITISNI ZA NAZAJ");
    lv_label_set_text(action_detail_label, "");
    lv_obj_add_flag(action_icon, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_text_color(action_label, lv_palette_main(LV_PALETTE_GREY), 0);
    return;
  }

  const bool shower_active = model.action == DisplayAction::CloseNow;
  const bool unavailable = !model.connected;
  const std::string title = shower_active
                                ? "TUŠ AKTIVEN"
                                : (unavailable ? "NI POVEZAVE" : "VODA ZAPRTA");
  const std::string summary = shower_active
                                  ? "SAMODEJNI IZKLOP VKLJUČEN"
                                  : (unavailable ? "PREVERI HUB" : model.forecast_summary_text);
  lv_label_set_text(state_label, title.c_str());
  lv_label_set_text(temperature_label, summary.c_str());
  lv_label_set_text(detail_label, "");
  lv_label_set_text(action_label, model.primary_action_text.c_str());
  lv_label_set_text(action_detail_label, model.primary_action_detail.c_str());
  if (!model.action_enabled) {
    lv_obj_add_flag(action_icon, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_text_color(action_label, lv_palette_main(LV_PALETTE_GREY), 0);
    return;
  }
  lv_obj_clear_flag(action_icon, LV_OBJ_FLAG_HIDDEN);
  const lv_color_t action_color = shower_active ? lv_color_hex(0xE5484D)
                                                 : lv_color_hex(0x20C9C3);
  lv_img_set_src(action_icon, shower_active ? &kStopIcon : &kShowerIcon);
  lv_obj_set_style_img_recolor(action_icon, action_color, 0);
  lv_obj_set_style_img_recolor_opa(action_icon, LV_OPA_COVER, 0);
  lv_obj_set_style_text_color(action_label, action_color, 0);
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

  const InputEvent dial_event =
      dial_button.update(digitalRead(BoardPins::kEncoderButton) == LOW, now);
  if (dial_event != InputEvent::None) {
    last_input_ms = now;
    return dial_event;
  }

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
