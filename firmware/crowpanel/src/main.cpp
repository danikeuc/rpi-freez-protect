#include <Arduino.h>
#include <WiFi.h>
#include <atomic>

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
int last_hub_http_status = 0;
unsigned long last_poll_ms = 0;
unsigned long last_hub_poll_completed_ms = 0;
unsigned long last_diagnostic_render_ms = 0;
bool has_hub_poll = false;
bool last_hub_payload_valid = false;
int last_rendered_wifi_status = -1;
int last_rendered_wifi_disconnect_reason = -1;
std::atomic<int> last_wifi_disconnect_reason{-1};
bool wifi_start_attempted = false;

void handle_wifi_event(WiFiEvent_t event, WiFiEventInfo_t info) {
  if (event == WiFiEvent_t::ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
    last_wifi_disconnect_reason.store(
        static_cast<int>(info.wifi_sta_disconnected.reason));
  }
}

void render() {
  const int wifi_status = static_cast<int>(WiFi.status());
  const bool wifi_connected = wifi_status == WL_CONNECTED;
  DisplayModel model = reduce_status(last_status, wifi_connected, hub_connected);
  if (!wifi_connected) {
    model.connection_detail_text = wifi_diagnostic_details(
        wifi_status, WiFi.localIP().toString().c_str(), WiFi.macAddress().c_str(),
        last_wifi_disconnect_reason.load(), last_hub_http_status,
        last_hub_payload_valid,
        has_hub_poll ? (millis() - last_hub_poll_completed_ms) / 1000UL : 0UL,
        has_hub_poll);
  }
  if (!model.connected) {
    model.connection_text = connection_diagnostic(
        wifi_connected, hub_connected, last_hub_http_status, wifi_status);
  }
  model.page = page;
  hardware_ui.render(model);
  last_diagnostic_render_ms = millis();
}

void connect_wifi() {
  if (wifi_start_attempted) {
    return;
  }
  wifi_start_attempted = true;
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.println("Wi-Fi: connecting");
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
  WiFi.onEvent(handle_wifi_event,
               WiFiEvent_t::ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
  connect_wifi();
  render();
  last_rendered_wifi_status = static_cast<int>(WiFi.status());
  last_rendered_wifi_disconnect_reason = last_wifi_disconnect_reason.load();
  Serial.println("Freeze Protect CrowPanel boot");
}

void loop() {
  const unsigned long now = millis();
  const int wifi_status = static_cast<int>(WiFi.status());
  const int disconnect_reason = last_wifi_disconnect_reason.load();
  if (wifi_status != last_rendered_wifi_status ||
      disconnect_reason != last_rendered_wifi_disconnect_reason) {
    last_rendered_wifi_status = wifi_status;
    last_rendered_wifi_disconnect_reason = disconnect_reason;
    if (wifi_status != WL_CONNECTED) {
      hub_connected = false;
    }
    Serial.printf("Wi-Fi status=%d IP=%s\n", wifi_status,
                  WiFi.localIP().toString().c_str());
    render();
  }
  if (wifi_status == WL_CONNECTED && now - last_poll_ms >= 5000) {
    const HubResult result = hub_client.poll();
    hub_connected = result.connected;
    last_hub_http_status = result.http_status;
    last_hub_payload_valid = result.connected;
    has_hub_poll = true;
    last_hub_poll_completed_ms = millis();
    Serial.printf("Wi-Fi: connected, IP=%s | Hub: HTTP=%d, payload=%s\n",
                  WiFi.localIP().toString().c_str(), result.http_status,
                  result.connected ? "valid" : "invalid");
    if (result.connected) {
      last_status = result.status;
    }
    last_poll_ms = millis();
    render();
  }
  if (wifi_status != WL_CONNECTED &&
      now - last_diagnostic_render_ms >= 1000) {
    render();
  }
  handle_input();
  hardware_ui.tick();
  delay(5);
}
