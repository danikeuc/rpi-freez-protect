#include <Arduino.h>
#include <WiFi.h>
#include <NetworkClient.h>
#include <lwip/sockets.h>
#include <cerrno>
#include <atomic>
#include "http_exchange.h"
#include "model.h"
#include "action.h"
#if GEN4_TOUCH
#include <gfx4desp32_gen4_ESP32_28CT.h>
#include "touch_sample.h"
gfx4desp32_gen4_ESP32_28CT display;
#else
#include <gfx4desp32_gen4_ESP32_28.h>
gfx4desp32_gen4_ESP32_28 display;
#endif
#ifndef GEN4_TEST_HUB
#define GEN4_TEST_HUB 0
#endif
#ifndef GEN4_OFFLINE_BENCH
#define GEN4_OFFLINE_BENCH 0
#endif
#ifndef GEN4_NETWORK_BENCH
#define GEN4_NETWORK_BENCH 0
#endif
#if GEN4_NETWORK_BENCH
#if GEN4_TOUCH || GEN4_OFFLINE_BENCH
#error Network bench requires the read-only network target
#endif
#include "network_bench.h"
#endif
#if !GEN4_OFFLINE_BENCH && __has_include("secrets.h")
#include "secrets.h"
#else
#define WIFI_SSID ""
#define WIFI_PASSWORD ""
#define HUB_BASE_URL ""
#define DISPLAY_TOKEN ""
#endif
#include "test_hub_config.h"
#if GEN4_TEST_HUB
#include "test_hub_contract.h"
#endif

namespace {
using namespace gen4;
constexpr char kStatusPath[] = "/api/v1/display/status";
#if GEN4_TEST_HUB
constexpr char kStartPath[] = "/api/v1/display/actions/timed-shower";
constexpr char kDrainPath[] = "/api/v1/display/actions/drain";
#endif
std::atomic<uint32_t> connection_generation{0};
#if GEN4_TEST_HUB
struct Request { Action action; uint32_t created_ms; uint32_t id; uint32_t generation; };
#endif
struct Snapshot {
  Status status{};
  bool valid = false;
  uint32_t received_ms = 0;
  int action_result = 0;
  uint32_t completed_id = 0;
  uint32_t generation = 0;
};
#if GEN4_TEST_HUB
QueueHandle_t requests = nullptr;
#endif
QueueHandle_t snapshots = nullptr;
Model model;
Gesture gesture;
int action_result = 0;
bool configured = false;
bool worker_ready = false;
#if GEN4_TEST_HUB
uint32_t test_starts = 0, test_drains = 0, test_pressed = 0, test_invalid = 0;
uint32_t test_last_sample = 0, test_max_gap = 0;
uint32_t test_gap_over100 = 0, test_start_zone = 0, test_drain_zone = 0;
uint32_t test_start_allowed = 0, test_other_zone = 0, test_last_x = 0, test_last_y = 0;
uint32_t test_press_gap_over100 = 0;
uint32_t test_max_render_ms = 0, test_render_over100 = 0, test_max_report_ms = 0;
#endif
#if GEN4_NETWORK_BENCH
NetworkBench network_bench;
std::atomic<uint32_t> bench_posts_blocked{0};
bool bench_disconnect_ok = false;
#endif
#if GEN4_OFFLINE_BENCH
uint32_t bench_pressed = 0, bench_invalid = 0, bench_actions = 0;
#endif

IPAddress hub_address;
uint16_t hub_port = 80;
String hub_authority;
uint32_t poll_started = 0;
#if GEN4_TOUCH && (GEN4_TEST_HUB || GEN4_OFFLINE_BENCH)
TouchReader<TwoWire> touch_reader(Wire);
uint8_t touch_address = 0;
#endif

bool parse_endpoint() {
  // DNS has no transaction deadline in NetworkClient. Use a fixed LAN IPv4.
  String base(HUB_BASE_URL);
  if (!base.startsWith("http://")) return false;
  base.remove(0, 7);
  if (base.endsWith("/")) base.remove(base.length() - 1);
  if (base.indexOf('/') >= 0) return false;
  hub_authority = base;
  const int colon = base.indexOf(':');
  if (colon >= 0) {
    const String port = base.substring(colon + 1);
    if (port.length() == 0 || port.length() > 5) return false;
    for (unsigned i = 0; i < port.length(); ++i)
      if (port[i] < '0' || port[i] > '9') return false;
    const long number = port.toInt();
    if (number < 1 || number > 65535) return false;
    hub_port = uint16_t(number);
    base = base.substring(0, colon);
  }
  if (!hub_address.fromString(base)) return false;
#if GEN4_TEST_HUB
  if (hub_port != 18081) return false;  // Never use the real gateway's port.
#endif
  const size_t token_size = strlen(DISPLAY_TOKEN);
  if (token_size == 0 || token_size > 256) return false;
  for (size_t i = 0; i < token_size; ++i)
    if (DISPLAY_TOKEN[i] <= 32 || DISPLAY_TOKEN[i] > 126) return false;
  return true;
}
// Sole network-task owner. Raw nonblocking socket I/O avoids the framework's
// per-chunk timeouts, hidden write retries and unbounded response-drain cleanup.
class HubSocket {
 public:
  explicit HubSocket(uint32_t generation) : generation_(generation) {}
  bool valid() const {
    return generation_ == connection_generation.load() && WiFi.status() == WL_CONNECTED;
  }
  bool connect(uint32_t timeout) {
    return valid() && client_.connect(hub_address, hub_port, int32_t(timeout)) == 1 && valid();
  }
  int send(const char* data, size_t size) {
    if (!valid()) return -2;
    const int n = ::send(client_.fd(), data, size, MSG_DONTWAIT);
    return n < 0 ? pending_or_error() : (n == 0 ? -2 : n);
  }
  int read() {
    if (!valid()) return -2;
    uint8_t value;
    const int n = ::recv(client_.fd(), &value, 1, MSG_DONTWAIT);
    return n < 0 ? pending_or_error() : (n == 0 ? -2 : value);
  }
  uint32_t now() { return millis(); }
  void idle() { vTaskDelay(1); }
  void stop() { client_.stop(); }
 private:
  uint32_t generation_;
  NetworkClient client_;
  static int pending_or_error() {
    return errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR ? -1 : -2;
  }
};
bool exchange(const char* path, bool post, String& body, uint32_t generation) {
#if GEN4_NETWORK_BENCH
  if (post) { ++bench_posts_blocked; return false; }
#endif
#if !GEN4_TEST_HUB
  // Ordinary images have no action transport, even if a future caller passes true.
  if (post) return false;
#endif
  if (WiFi.status() != WL_CONNECTED) return false;
#if GEN4_TEST_HUB
  String request = post ? "POST " : "GET ";
#else
  String request = "GET ";
#endif
  request += path;
  request += " HTTP/1.0\r\nHost: ";
  request += hub_authority;
  request += "\r\nX-Display-Token: ";
  request += DISPLAY_TOKEN;
  request += "\r\nAccept: application/json\r\nConnection: close\r\n";
#if GEN4_TEST_HUB
  if (post) request += "Content-Length: 0\r\n";
#endif
  request += "\r\n";
  HubSocket socket(generation);
  char buffer[4097];
  size_t length = 0;
  uint32_t started;
  const bool ok = http_exchange(socket, request.c_str(), buffer, sizeof(buffer), length, started);
  if (!post) poll_started = started;
#if GEN4_TEST_HUB
  if (ok && !is_test_hub_response(buffer, length)) return false;
#endif
  if (ok) body.concat(buffer, length);
  return ok;
}
bool poll(Status& status, uint32_t generation) {
  String body;
  return exchange(kStatusPath, false, body, generation) &&
         parse_status(body.c_str(), body.length(), status);
}
#if GEN4_TEST_HUB
class HubTransport : public Transport {
 public:
  explicit HubTransport(uint32_t generation) : generation_(generation) {}
  bool session_valid() const override {
    return generation_ == connection_generation.load() && WiFi.status() == WL_CONNECTED;
  }
  bool status(Status& out) override { return poll(out, generation_); }
  bool post(Action action) override {
    String receipt;
    return session_valid() &&
           exchange(action == Action::Start ? kStartPath : kDrainPath, true, receipt, generation_) &&
           session_valid() && valid_receipt(receipt.c_str(), receipt.length(), action);
  }
 private:
  uint32_t generation_;
};
uint32_t now_ms() { return millis(); }
#endif
void network_task(void*) {
#if GEN4_TEST_HUB
  int last_result = 0;
  uint32_t completed_id = 0;
#endif
  uint32_t last_poll = millis() - 2000;
  for (;;) {
#if GEN4_TEST_HUB
    Request request{};
    const bool have_request = xQueueReceive(requests, &request, pdMS_TO_TICKS(20)) == pdTRUE;
    if (!have_request && uint32_t(millis() - last_poll) < 2000) continue;
#else
    vTaskDelay(pdMS_TO_TICKS(20));
    if (uint32_t(millis() - last_poll) < 2000) continue;
#endif
    Snapshot result;
    result.generation = connection_generation.load();
#if GEN4_TEST_HUB
    if (have_request) {
      HubTransport transport(request.generation);
      // Never replay a queued action after reconnection. Recheck server
      // permission immediately before START; POST actions are never retried.
      const bool accepted = WiFi.status() == WL_CONNECTED &&
          send_action(request.action, request.created_ms, now_ms, transport);
      last_result = accepted ? 1 : -1;
      completed_id = request.id;
      // A failed receipt stops this action path. A later periodic status poll
      // may reconcile state, but cannot resend the action.
      if (accepted) result.valid = poll(result.status, result.generation);
    } else {
      result.valid = poll(result.status, result.generation);
    }
#else
    result.valid = poll(result.status, result.generation);
#endif
    result.received_ms = poll_started;  // Include request time in freshness/countdown.
#if GEN4_TEST_HUB
    result.action_result = last_result;
    result.completed_id = completed_id;
#endif
    xQueueOverwrite(snapshots, &result);
    last_poll = millis();
  }
}

void text(int x, int y, const char* value, int size = 1, uint16_t color = 0xFFFF) {
  display.TextSize(size);
  display.TextColor(color, 0x0841);
  display.MoveTo(x, y);
  display.print(value);
}
void render(uint32_t now) {
  display.Cls(0x0841);
  text(14, 12, "FREEZE PROTECT", 2, 0x4E79);
#if GEN4_TEST_HUB
  text(14, 36, "SIMULACIJA - BREZ VENTILOV");
#elif GEN4_OFFLINE_BENCH
  text(14, 36, "OFFLINE PREIZKUS");
#elif GEN4_NETWORK_BENCH
  text(14, 36, "PREIZKUS POVEZAVE");
#else
  text(14, 36, "gen4 ESP32 2.8");
#endif
  const bool fresh = WiFi.status() == WL_CONNECTED && model.fresh(now);
  if (!configured) {
    text(14, 80, "NASTAVI POVEZAVO", 2);
    text(14, 118, "Wi-Fi in Hub nista nastavljena.");
  } else if (!worker_ready) {
    text(14, 80, "NAPAKA ZAGONA", 2);
  } else if (model.pending) {
    text(14, 80, "CAKAM NA HUB", 2);
  } else if (!fresh) {
    text(14, 80, "NI POVEZAVE", 2);
    text(14, 118, "Stanje ni znano.");
  } else {
    text(14, 70, model.status.command == Command::Supply ? "UKAZ: SUPPLY" : "UKAZ: DRAIN", 2);
    char timer[32];
    const int seconds = model.remaining(now);
    snprintf(timer, sizeof(timer), "Preostalo %02d:%02d", seconds / 60, seconds % 60);
    text(14, 104, timer, 2);
    text(14, 136, model.status.manual ? "Casovnik vodi Hub." : "Nacin samo za prikaz.");
  }
  if (action_result < 0) text(14, 160, "Ukaz ni potrjen. Preveri stanje.", 1, 0xFAAA);
#if GEN4_TOUCH && (GEN4_TEST_HUB || GEN4_OFFLINE_BENCH)
  const bool start = fresh && model.can_start(now);
  display.RectangleFilled(12, 190, 227, 239, start ? 0x032C : 0x2104);
  text(28, 205, start ? "DRZI 2s ZA TUS" : "TUS NI NA VOLJO", 2);
  display.RectangleFilled(12, 248, 227, 287, fresh ? 0x7800 : 0x2104);
  text(48, 260, "IZPUST", 2);
#else
  text(14, 212, "SAMO PRIKAZ", 2);
  text(14, 244, "Izvedba brez dotika.");
#endif
  text(14, 302, "Polozaj ventilov ni merjen.");
}
}  // namespace

void setup() {
  Serial.begin(115200);
  Serial.println("Freeze Protect gen4-ESP32-28 / v1");
  // Official board class owns LCD, touch and backlight pin assignments.
  display.begin();
  display.Orientation(PORTRAIT);
  display.Font(1);
  display.TextSize(1);
  display.BacklightOn(true);
#if GEN4_TOUCH && (GEN4_TEST_HUB || GEN4_OFFLINE_BENCH)
  display.touch_Set(TOUCH_ENABLE);
  Wire.setTimeOut(20);
  if (display.t_controller == 0) touch_address = 0x38;
  else {
    for (uint8_t address : {uint8_t(0x5d), uint8_t(0x14)}) {
      Wire.beginTransmission(address);
      if (Wire.endTransmission() == 0) { touch_address = address; break; }
    }
  }
#endif
#if GEN4_OFFLINE_BENCH
  configured = false;  // This target can never provision a network worker.
#else
  configured = strlen(WIFI_SSID) > 0 && parse_endpoint();
#endif
  if (configured) {
    WiFi.persistent(false);
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t) {
      if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) ++connection_generation;
    });
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
#if GEN4_TEST_HUB
    requests = xQueueCreate(1, sizeof(Request));
#endif
    snapshots = xQueueCreate(1, sizeof(Snapshot));
#if GEN4_TEST_HUB
    if (requests && snapshots)
#else
    if (snapshots)
#endif
      worker_ready = xTaskCreate(network_task, "hub-client", 12288, nullptr, 1, nullptr) == pdPASS;
  }
  render(millis());
#if GEN4_OFFLINE_BENCH
  Serial.printf("GEN4_APP_READY v1 touch=%u configured=%u worker=%u offline=1\n",
                unsigned(GEN4_TOUCH), unsigned(configured), unsigned(worker_ready));
#endif
}
void loop() {
  Snapshot snapshot;
  bool changed = false;
  static uint32_t ui_generation = 0;
  const uint32_t generation = connection_generation.load();
  if (generation != ui_generation) {
    ui_generation = generation;
    model.valid = false;
    gesture = Gesture{};
    changed = true;
  }
  if (worker_ready && xQueueReceive(snapshots, &snapshot, 0) == pdTRUE) {
    if (model.accept(snapshot.status, snapshot.valid && snapshot.generation == generation,
                     snapshot.received_ms, snapshot.completed_id)) {
      action_result = snapshot.action_result;
      changed = true;
    }
  }
  // Sample time after receiving a worker snapshot: its timestamp must not
  // appear to be in the future and spuriously cancel an in-progress hold.
  const uint32_t now = millis();
  if (WiFi.status() != WL_CONNECTED) model.valid = false;
#if GEN4_TOUCH && (GEN4_TEST_HUB || GEN4_OFFLINE_BENCH)
  const TouchSample sample = touch_reader.read(display.t_controller, touch_address);
#if GEN4_TEST_HUB
  const uint32_t sample_ms = millis();
  const uint32_t sample_gap = test_last_sample ? uint32_t(sample_ms - test_last_sample) : 0;
  if (sample_gap > test_max_gap) test_max_gap = sample_gap;
  if (sample_gap > 100) {
    ++test_gap_over100;
    if (sample.state == TouchState::kPressed) ++test_press_gap_over100;
  }
  test_last_sample = sample_ms;
  if (sample.state == TouchState::kPressed) ++test_pressed;
  if (sample.state == TouchState::kInvalid) ++test_invalid;
#endif
#if GEN4_OFFLINE_BENCH
  if (sample.state == TouchState::kPressed) ++bench_pressed;
  if (sample.state == TouchState::kInvalid) ++bench_invalid;
#endif
  const bool down = sample.state == TouchState::kPressed;
  const int x = sample.x;
  const int y = sample.y;
  Action target = Action::None;
  if (x >= 12 && x <= 227) {
    if (y >= 190 && y <= 239) target = Action::Start;
    if (y >= 248 && y <= 287) target = Action::Drain;
  }
#if GEN4_TEST_HUB
  if (sample.state == TouchState::kPressed) {
    test_last_x = x;
    test_last_y = y;
    if (target == Action::Start) {
      ++test_start_zone;
      if (model.can_start(now)) ++test_start_allowed;
    } else if (target == Action::Drain) ++test_drain_zone;
    else ++test_other_zone;
  }
#endif
  // No-ready GT frames do not refresh the sample lease. The next valid sample
  // cancels any hold if the gap exceeds 100 ms; failed I2C reads cancel at once.
  const Action action = sample.state == TouchState::kWaiting ? Action::None :
      gesture.update(down, target, model, millis(), sample.state != TouchState::kInvalid);
#if GEN4_OFFLINE_BENCH
  if (action != Action::None) ++bench_actions;
#endif
#if GEN4_TEST_HUB
  if (action == Action::Start) ++test_starts;
  if (action == Action::Drain) ++test_drains;
#endif
#if GEN4_TEST_HUB
  if (action != Action::None && worker_ready) {
    const Request request{action, now, model.begin_request(), generation};
    if (xQueueSend(requests, &request, 0) != pdTRUE) {
      model.pending = false;
      action_result = -1;
    }
    changed = true;
  }
#endif
#endif
  static uint32_t last_render = 0;
  if (should_render(changed, millis(), last_render, gesture, model)) {
    const uint32_t render_begin = millis();
    render(render_begin);
    const uint32_t render_done = millis();
    last_render = render_done;
#if GEN4_TEST_HUB
    const uint32_t render_ms = uint32_t(render_done - render_begin);
    if (render_ms > test_max_render_ms) test_max_render_ms = render_ms;
    if (render_ms > 100) ++test_render_over100;
#endif
  }
#if GEN4_OFFLINE_BENCH
  static uint32_t last_report = 0;
  if (uint32_t(now - last_report) >= 5000) {
    last_report = now;
    Serial.printf("GEN4_APP_BENCH uptime_ms=%lu pressed=%lu invalid=%lu actions=%lu configured=%u worker=%u\n",
                  (unsigned long)now, (unsigned long)bench_pressed,
                  (unsigned long)bench_invalid, (unsigned long)bench_actions,
                  unsigned(configured), unsigned(worker_ready));
  }
#endif
#if GEN4_NETWORK_BENCH
  // Serial n starts one bounded outage only after a fresh authenticated poll.
  // It never changes Hub state, credentials, model validity or action intent.
  if (Serial.available() > 0 && Serial.read() == 'n' &&
      network_bench.begin(millis(), WiFi.status() == WL_CONNECTED, model.fresh(millis()))) {
    WiFi.setAutoReconnect(false);
    bench_disconnect_ok = WiFi.disconnect(false, false);
    network_bench.disconnected(bench_disconnect_ok);
  }
  if (network_bench.reconnect_due(millis(), WiFi.status() == WL_CONNECTED, model.fresh(millis()))) {
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
  static uint32_t last_network_report = 0;
  if (uint32_t(millis() - last_network_report) >= 1000) {
    last_network_report = millis();
    const bool connected = WiFi.status() == WL_CONNECTED;
    Serial.printf("GEN4_NETWORK ms=%lu phase=%u wifi=%u fresh=%u gen=%lu post_blocked=%lu disconnect_ok=%u\n",
                  (unsigned long)millis(), network_bench.phase(), unsigned(connected),
                  unsigned(connected && model.fresh(millis())),
                  (unsigned long)connection_generation.load(),
                  (unsigned long)bench_posts_blocked.load(), unsigned(bench_disconnect_ok));
  }
#endif
#if GEN4_TEST_HUB
  static uint32_t last_test_report = 0;
  if (uint32_t(millis() - last_test_report) >= 1000) {
    const uint32_t report_begin = millis();
    // USB logging is diagnostic only. Never block a live hold or touch sampling.
    if (Serial && !gesture.holding_start(report_begin)) {
      char report[256];
      const int n = snprintf(report, sizeof(report),
          "GEN4_DIAG ms=%lu w=%u f=%u q=%u rc=%d s=%lu d=%lu p=%lu i=%lu sz=%lu dz=%lu az=%lu oz=%lu g=%lu pg=%lu rm=%lu r100=%lu sm=%lu x=%lu y=%lu\n",
          (unsigned long)millis(), unsigned(WiFi.status() == WL_CONNECTED),
          unsigned(model.fresh(millis())), unsigned(model.pending), action_result,
          (unsigned long)test_starts, (unsigned long)test_drains,
          (unsigned long)test_pressed, (unsigned long)test_invalid,
          (unsigned long)test_start_zone, (unsigned long)test_drain_zone,
          (unsigned long)test_start_allowed, (unsigned long)test_other_zone,
          (unsigned long)test_gap_over100, (unsigned long)test_press_gap_over100,
          (unsigned long)test_max_render_ms, (unsigned long)test_render_over100,
          (unsigned long)test_max_report_ms,
          (unsigned long)test_last_x, (unsigned long)test_last_y);
      if (n > 0 && size_t(n) < sizeof(report) &&
          Serial.availableForWrite() >= n)
        Serial.write(reinterpret_cast<const uint8_t*>(report), size_t(n));
    }
    const uint32_t report_ms = uint32_t(millis() - report_begin);
    if (report_ms > test_max_report_ms) test_max_report_ms = report_ms;
    last_test_report = millis();
  }
#endif
  delay(10);
}
