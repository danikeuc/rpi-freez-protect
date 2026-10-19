#pragma once
#include <deque>
#include <vector>
#include <algorithm>
#include "touch_sample.h"
#include "http_exchange.h"

struct WireReply {
  uint16_t reg;
  std::vector<uint8_t> bytes;
  int ack = 0;
  WireReply(uint16_t r, std::vector<uint8_t> b, int a = 0) : reg(r), bytes(b), ack(a) {}
};
struct FakeWire {
  std::deque<WireReply> replies;
  std::vector<uint8_t> sent, received;
  size_t pos = 0;
  int ack_result = 0;
  void beginTransmission(uint8_t) { sent.clear(); }
  size_t write(uint8_t value) { sent.push_back(value); return 1; }
  int endTransmission(bool stop = true) {
    if (stop) {
      TEST_ASSERT_EQUAL(3, sent.size());
      TEST_ASSERT_EQUAL_HEX8(0x81, sent[0]);
      TEST_ASSERT_EQUAL_HEX8(0x4e, sent[1]);
      TEST_ASSERT_EQUAL(0, sent[2]);
      return ack_result;
    }
    TEST_ASSERT_FALSE(replies.empty());
    const uint16_t reg = sent.size() == 2 ? (sent[0] << 8) | sent[1] : sent[0];
    TEST_ASSERT_EQUAL_HEX16(replies.front().reg, reg);
    return replies.front().ack;
  }
  size_t requestFrom(uint8_t, size_t) {
    received = replies.front().bytes;
    replies.pop_front();
    pos = 0;
    return received.size();
  }
  int available() { return int(received.size() - pos); }
  int read() { return pos < received.size() ? received[pos++] : -1; }
};
void failed_touch_read_disarms_until_verified_release() {
  FakeWire wire;
  TouchReader<FakeWire> reader(wire);
  Gesture gesture;
  Model model = ready();
  // Full release, then a valid START sample, then a truncated I2C response.
  wire.replies.emplace_back(2, std::vector<uint8_t>{0, 0, 0, 0, 0, 0});
  auto sample = reader.read(0, 0x38);
  gesture.update(false, Action::None, model, 0, sample.state == TouchState::kReleased);
  wire.replies.emplace_back(2, std::vector<uint8_t>{1, 0, 100, 0, 210, 0});
  sample = reader.read(0, 0x38);
  TEST_ASSERT_EQUAL_INT(int(TouchState::kPressed), int(sample.state));
  TEST_ASSERT_EQUAL(100, sample.x);
  TEST_ASSERT_EQUAL(210, sample.y);
  gesture.update(true, Action::Start, model, 10);
  wire.replies.emplace_back(2, std::vector<uint8_t>{1, 0});
  sample = reader.read(0, 0x38);
  TEST_ASSERT_EQUAL_INT(int(TouchState::kInvalid), int(sample.state));
  gesture.update(false, Action::None, model, 20, false);
  // Recovery with the finger still held must not re-arm or emit an action.
  for (uint32_t t = 30; t <= 4030; t += 50)
    TEST_ASSERT_EQUAL_INT(int(Action::None), int(gesture.update(true, Action::Start, model, t)));
  gesture.update(false, Action::None, model, 4040);
  TEST_ASSERT_EQUAL_INT(int(Action::Drain), int(gesture.update(true, Action::Drain, model, 4050)));
}
void touch_rejects_nack_multi_and_outside_screen() {
  for (const auto& bytes : {std::vector<uint8_t>{}, {2,0,100,0,210,0},
                           {1,1,0,0,210,0}, {1,0,100,1,64,0}}) {
    FakeWire wire;
    TouchReader<FakeWire> reader(wire);
    wire.replies.emplace_back(2, bytes);
    TEST_ASSERT_EQUAL_INT(int(TouchState::kInvalid), int(reader.read(0,0x38).state));
  }
  FakeWire wire;
  TouchReader<FakeWire> reader(wire);
  wire.replies.emplace_back(2, std::vector<uint8_t>{1,0,100,0,210,0}, 4);
  TEST_ASSERT_EQUAL_INT(int(TouchState::kInvalid), int(reader.read(0,0x38).state));
}
void gt_touch_requires_ready_complete_sample_and_ack() {
  FakeWire wire;
  TouchReader<FakeWire> reader(wire);
  wire.replies.emplace_back(0x814e, std::vector<uint8_t>{0});
  TEST_ASSERT_EQUAL_INT(int(TouchState::kWaiting), int(reader.read(1,0x5d).state));
  wire.replies.emplace_back(0x814e, std::vector<uint8_t>{0x81});
  wire.replies.emplace_back(0x814f, std::vector<uint8_t>{0,100,0,210,0,0,0,0});
  auto sample = reader.read(1,0x5d);
  TEST_ASSERT_EQUAL_INT(int(TouchState::kPressed), int(sample.state));
  TEST_ASSERT_EQUAL(100, sample.x);
  TEST_ASSERT_EQUAL(210, sample.y);
  wire.replies.emplace_back(0x814e, std::vector<uint8_t>{0x81});
  wire.replies.emplace_back(0x814f, std::vector<uint8_t>{0,100});
  TEST_ASSERT_EQUAL_INT(int(TouchState::kInvalid), int(reader.read(1,0x5d).state));
  wire.replies.emplace_back(0x814e, std::vector<uint8_t>{0x80});
  wire.ack_result = 4;
  TEST_ASSERT_EQUAL_INT(int(TouchState::kInvalid), int(reader.read(1,0x5d).state));
  wire.replies.emplace_back(0x814e, std::vector<uint8_t>{0x80});
  wire.ack_result = 0;
  TEST_ASSERT_EQUAL_INT(int(TouchState::kReleased), int(reader.read(1,0x5d).state));
}
struct FakeSocket {
  std::string response = "HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\n{}";
  std::string written;
  uint32_t tick = 0, origin = 0, spacing = 0, first_byte = 0, write_wait = 0;
  size_t position = 0;
  int connections = 0;
  bool closed = false, eof = false;
  bool connect(uint32_t) { ++connections; origin = tick; return true; }
  int send(const char* data, size_t size) {
    if (uint32_t(tick - origin) < write_wait) return -1;
    const size_t n = std::min(size, size_t(3));
    written.append(data, n);
    return int(n);
  }
  int read() {
    if (position == response.size()) return eof ? -2 : -1;
    if (uint32_t(tick - origin) < first_byte + uint32_t(position) * spacing) return -1;
    return static_cast<unsigned char>(response[position++]);
  }
  uint32_t now() { return tick; }
  void idle() { ++tick; }
  void stop() { closed = true; }
};
bool run_exchange(FakeSocket& socket, uint32_t* start = nullptr) {
  char body[4097];
  size_t size = 999;
  uint32_t started;
  const bool ok = http_exchange(socket, "POST /test HTTP/1.0\r\nContent-Length: 0\r\n\r\n",
                                body, sizeof(body), size, started);
  if (start) *start = started;
  TEST_ASSERT_TRUE(socket.closed);
  if (ok) {
    TEST_ASSERT_EQUAL(2, size);
    TEST_ASSERT_EQUAL_STRING("{}", body);
  } else TEST_ASSERT_EQUAL(0, size);
  return ok;
}
void fragmented_http_and_partial_writes_preserve_one_request() {
  FakeSocket socket;
  socket.tick = 100;
  socket.spacing = 10;
  uint32_t started;
  TEST_ASSERT_TRUE(run_exchange(socket, &started));
  TEST_ASSERT_EQUAL(100, started);
  TEST_ASSERT_EQUAL(1, socket.connections);
  TEST_ASSERT_EQUAL_STRING("POST /test HTTP/1.0\r\nContent-Length: 0\r\n\r\n", socket.written.c_str());
}
void slow_headers_body_and_writes_hit_absolute_deadline() {
  FakeSocket headers;
  headers.spacing = 100;
  TEST_ASSERT_FALSE(run_exchange(headers));
  TEST_ASSERT_EQUAL(2000, headers.tick);
  FakeSocket body;
  body.spacing = 50; // Header and first body byte arrive, final byte is too late.
  body.first_byte = 100;
  TEST_ASSERT_FALSE(run_exchange(body));
  TEST_ASSERT_EQUAL(2000, body.tick);
  FakeSocket writes;
  writes.write_wait = 5000;
  TEST_ASSERT_FALSE(run_exchange(writes));
  TEST_ASSERT_EQUAL(2000, writes.tick);
  TEST_ASSERT_EQUAL(1, writes.connections);
  TEST_ASSERT_EQUAL(0, writes.written.size());
  FakeSocket wrap;
  wrap.tick = 0xffffff00u;
  wrap.first_byte = 3000;
  TEST_ASSERT_FALSE(run_exchange(wrap));
  TEST_ASSERT_EQUAL_UINT32(uint32_t(0xffffff00u + 2000), wrap.tick);
}
void malformed_truncated_or_unbounded_http_is_rejected() {
  for (const auto& response : {
      std::string("HTTP/1.0 302 Found\r\nContent-Length: 2\r\n\r\n{}"),
      std::string("HTTP/1.0 200 OK\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}"),
      std::string("HTTP/1.0 200 OK\r\nTransfer-Encoding: chunked\r\nContent-Length: 2\r\n\r\n{}"),
      std::string("HTTP/1.0 200 OK\r\nContent-Length: 4097\r\n\r\n"),
      std::string("HTTP/1.0 200 OK\r\n\r\n{}"),
      std::string("HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\n{"),
      std::string("HTTP/1.0 200 OK\r\nX: ") + std::string(3000,'a')}) {
    FakeSocket socket;
    socket.response = response;
    socket.eof = true;
    TEST_ASSERT_FALSE(run_exchange(socket));
    TEST_ASSERT_EQUAL(1, socket.connections);
  }
}
void run_transport_tests() {
  RUN_TEST(failed_touch_read_disarms_until_verified_release);
  RUN_TEST(touch_rejects_nack_multi_and_outside_screen);
  RUN_TEST(gt_touch_requires_ready_complete_sample_and_ack);
  RUN_TEST(fragmented_http_and_partial_writes_preserve_one_request);
  RUN_TEST(slow_headers_body_and_writes_hit_absolute_deadline);
  RUN_TEST(malformed_truncated_or_unbounded_http_is_rejected);
}
