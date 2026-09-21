#include <Arduino.h>
#include <WiFi.h>

#include "board_pins.h"
#include "display_state.h"
#include "hardware.h"
#include "hub_client.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Copy include/secrets.example.h to include/secrets.h and provision local credentials."
#endif

namespace {

HardwareUi hardware_ui;
HubClient hub_client(HUB_BASE_URL, DISPLAY_TOKEN);
HubStatus last_status{};
DisplayPage page = DisplayPage::Home;
bool hub_connected = false;
unsigned long last_poll_ms = 0;
unsigned long last_wifi_attempt_ms = 0;

void render() {
  DisplayModel model = reduce_status(last_status, WiFi.status() == WL_CONNECTED,
                                     hub_connected);
  model.page = page;
  hardware_ui.render(model);
}

void connect_wifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  last_wifi_attempt_ms = millis();
}

void handle_input() {
  const InputEvent input = hardware_ui.poll_input();
  if (input == InputEvent::SafetyDrain) {
    hub_client.drain();
    last_poll_ms = 0;
    return;
  }
  if (input == InputEvent::NextPage) {
    page = move_page(page, true);
    render();
    return;
  }
  if (input == InputEvent::PreviousPage) {
    page = move_page(page, false);
    render();
    return;
  }
  if (input != InputEvent::PrimaryAction) {
    return;
  }
  const DisplayModel model = reduce_status(last_status,
                                           WiFi.status() == WL_CONNECTED,
                                           hub_connected);
  const DisplayInteraction interaction = primary_press(page, model);
  if (interaction == DisplayInteraction::ShowHome) {
    page = DisplayPage::Home;
    render();
    return;
  }
  if (interaction == DisplayInteraction::TimedShower) {
    hub_client.start_timed_shower();
  } else if (interaction == DisplayInteraction::Drain) {
    hub_client.drain();
  } else {
    return;
  }
  last_poll_ms = 0;
}

}  // namespace

void setup() {
  Serial.begin(115200);
  hardware_ui.begin();
  connect_wifi();
  render();
  Serial.println("Freeze Protect CrowPanel boot");
}

void loop() {
  const unsigned long now = millis();
  if (WiFi.status() != WL_CONNECTED && now - last_wifi_attempt_ms > 10000) {
    hub_connected = false;
    connect_wifi();
    render();
  }
  if (WiFi.status() == WL_CONNECTED && now - last_poll_ms >= 5000) {
    const HubResult result = hub_client.poll();
    hub_connected = result.connected;
    if (result.connected) {
      last_status = result.status;
    }
    last_poll_ms = now;
    render();
  }
  handle_input();
  hardware_ui.tick();
  delay(5);
}
