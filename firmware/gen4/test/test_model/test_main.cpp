#include <unity.h>
#include <cstring>
#include <string>
#include "model.h"
#include "action.h"
using namespace gen4;

const char* idle = R"({"mode":"manual_timed","command":"DRAIN","remaining_seconds":0,"state":"MANUAL_DRAIN","reason":"manual_idle","action":"TIMED_SHOWER","action_enabled":true})";
Model ready(uint32_t when = 0) {
  Model m;
  m.valid = parse_status(idle, std::strlen(idle), m.status);
  m.received_ms = when;
  return m;
}
void setUp() {}
void tearDown() {}
void parses_hub_contract() {
  Model m = ready();
  TEST_ASSERT_TRUE(m.can_start(0));
  TEST_ASSERT_EQUAL(0, m.remaining(0));
  const char* active = R"({"mode":"manual_timed","command":"SUPPLY","remaining_seconds":600,"state":"TIMED_SHOWER","reason":"manual_timed_shower","action":"CLOSE_NOW","action_enabled":true})";
  TEST_ASSERT_TRUE(parse_status(active, std::strlen(active), m.status));
  TEST_ASSERT_FALSE(m.can_start(0));
  TEST_ASSERT_EQUAL(598, m.remaining(2100));
}
void rejects_bad_status_and_clears_old_permissions() {
  const char* invalid[] = {"null", "[]", "{}", "{", R"({"state":"MANUAL_DRAIN","action_enabled":true})"};
  for (auto json : invalid) {
    Model m = ready();
    TEST_ASSERT_FALSE(parse_status(json, std::strlen(json), m.status));
    TEST_ASSERT_FALSE(m.status.may_start);
    TEST_ASSERT_EQUAL_INT(int(Command::Unknown), int(m.status.command));
  }
  const char* old_values[] = {"manual_timed", "DRAIN", "TIMED_SHOWER", "true", "\"remaining_seconds\":0"};
  const char* bad_values[] = {"unknown", "MIXED", "SUPPLY", "\"true\"", "\"remaining_seconds\":-1"};
  for (int i = 0; i < 5; ++i) {
    std::string payload(idle);
    payload.replace(payload.find(old_values[i]), std::strlen(old_values[i]), bad_values[i]);
    Status status;
    TEST_ASSERT_FALSE(parse_status(payload.c_str(), payload.size(), status));
  }
}
void safe_and_automatic_modes_cannot_start() {
  for (auto mode : {"safe_drain", "automatic"}) {
    std::string payload(idle);
    payload.replace(payload.find("manual_timed"), 12, mode);
    Model m;
    m.valid = parse_status(payload.c_str(), payload.size(), m.status);
    TEST_ASSERT_TRUE(m.valid);
    TEST_ASSERT_FALSE(m.can_start(0));
  }
}
void weather_assisted_status_is_display_only() {
  // Live display endpoint reports weather_assisted. Even a manual-looking
  // state and enabled action must not grant START in this mode.
  std::string payload(idle);
  payload.replace(payload.find("manual_timed"), 12, "weather_assisted");
  Model m;
  m.valid = parse_status(payload.c_str(), payload.size(), m.status);
  TEST_ASSERT_TRUE(m.valid);
  TEST_ASSERT_FALSE(m.status.manual);
  TEST_ASSERT_FALSE(m.can_start(0));
  TEST_ASSERT_EQUAL(0, m.remaining(0));
  payload.replace(payload.find("weather_assisted"), 16, "future_mode");
  TEST_ASSERT_FALSE(parse_status(payload.c_str(), payload.size(), m.status));
  TEST_ASSERT_FALSE(m.status.may_start);
}
void weather_assisted_accepts_hub_maximum_countdown() {
  const char* active = R"({"mode":"weather_assisted","command":"SUPPLY","remaining_seconds":1800,"state":"TIMED_SHOWER","reason":"weather_shower","action":"CLOSE_NOW","action_enabled":true})";
  Model m;
  m.valid = parse_status(active, std::strlen(active), m.status);
  TEST_ASSERT_TRUE(m.valid);
  TEST_ASSERT_FALSE(m.can_start(0));
  TEST_ASSERT_EQUAL(1800, m.remaining(0));
  std::string too_long(active);
  too_long.replace(too_long.find("1800"), 4, "1801");
  TEST_ASSERT_FALSE(parse_status(too_long.c_str(), too_long.size(), m.status));
  std::string manual(active);
  manual.replace(manual.find("weather_assisted"), 16, "manual_timed");
  manual.replace(manual.find("1800"), 4, "601");
  TEST_ASSERT_FALSE(parse_status(manual.c_str(), manual.size(), m.status));
}
void stale_pending_and_wraparound() {
  Model m = ready(0xFFFFFF00u);
  TEST_ASSERT_TRUE(m.can_start(0x00000020u));
  TEST_ASSERT_FALSE(m.can_start(uint32_t(0xFFFFFF00u + kStaleMs)));
  TEST_ASSERT_EQUAL(-1, m.remaining(uint32_t(0xFFFFFF00u + kStaleMs)));
  m.pending = true;
  TEST_ASSERT_FALSE(m.can_start(0x00000020u));
}
void gesture_requires_release_hold_and_one_action() {
  Gesture g;
  Model m = ready();
  TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(true, Action::Start, m, 0)));
  g.update(false, Action::None, m, 1);
  TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(true, Action::Start, m, 100)));
  for (uint32_t t = 150; t < 2100; t += 50)
    TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(true, Action::Start, m, t)));
  TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(true, Action::Start, m, 2099)));
  TEST_ASSERT_EQUAL_INT(int(Action::Start), int(g.update(true, Action::Start, m, 2100)));
  TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(true, Action::Start, m, 4200)));
}
void gesture_cancels_on_move_disconnect_and_recovery() {
  Gesture g;
  Model m = ready();
  g.update(false, Action::None, m, 0);
  g.update(true, Action::Start, m, 1);
  TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(true, Action::Drain, m, 500)));
  TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(true, Action::Start, m, 2200)));
  g.update(false, Action::None, m, 2300);
  g.update(true, Action::Start, m, 2400);
  m.valid = false;
  TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(true, Action::Start, m, 2500)));
  m = ready(2600);
  TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(true, Action::Start, m, 4600)));
  g.update(false, Action::None, m, 4601);
  TEST_ASSERT_EQUAL_INT(int(Action::Drain), int(g.update(true, Action::Drain, m, 4602)));
  TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(true, Action::Drain, m, 4603)));
}
void render_is_deferred_only_during_valid_start_hold() {
  Model m = ready();
  Gesture g;
  g.update(false, Action::None, m, 0);
  g.update(true, Action::Start, m, 10);
  for (uint32_t t = 60; t <= 1010; t += 50)
    TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(true, Action::Start, m, t)));
  TEST_ASSERT_FALSE(should_render(true, 1010, 0, g, m));
  // A GT "waiting" frame supplies no sample; the hold lease must expire.
  TEST_ASSERT_TRUE(should_render(false, 1111, 0, g, m));
  TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(true, Action::Start, m, 1211)));
  TEST_ASSERT_FALSE(g.holding_start(1211));
  TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(true, Action::Start, m, 2210)));
  TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(false, Action::None, m, 2211)));
  m.valid = false;
  TEST_ASSERT_TRUE(should_render(true, 3010, 0, g, m));
  m = ready(3010);
  g.update(false, Action::None, m, 3011);
  TEST_ASSERT_TRUE(should_render(false, 4011, 3011, g, m));
}
void unsampled_gap_cannot_complete_hold() {
  Gesture g;
  Model m = ready();
  g.update(false, Action::None, m, 0);
  g.update(true, Action::Start, m, 10);
  // UI/sensor stalls for longer than a valid sample lease.
  TEST_ASSERT_EQUAL_INT(int(Action::None), int(g.update(true, Action::Start, m, 2010)));
}
void receipts_must_match_action() {
  const char* start = R"({"state":"TIMED_SHOWER","command":"SUPPLY","reason":"manual_timed_shower"})";
  const char* drain = R"({"state":"MANUAL_DRAIN","command":"DRAIN","reason":"display_drain_requested"})";
  const char* fault = R"({"state":"FAULT","command":"DRAIN","reason":"failed"})";
  TEST_ASSERT_TRUE(valid_receipt(start, std::strlen(start), Action::Start));
  TEST_ASSERT_TRUE(valid_receipt(drain, std::strlen(drain), Action::Drain));
  TEST_ASSERT_FALSE(valid_receipt(start, std::strlen(start), Action::Drain));
  TEST_ASSERT_FALSE(valid_receipt(drain, std::strlen(drain), Action::Start));
  TEST_ASSERT_FALSE(valid_receipt(fault, std::strlen(fault), Action::Drain));
  TEST_ASSERT_FALSE(valid_receipt("{}", 2, Action::Start));
}
void delayed_poll_cannot_clear_pending_action() {
  Model m = ready();
  const Status idle_status = m.status;
  const uint32_t id = m.begin_request();
  TEST_ASSERT_FALSE(m.accept(idle_status, true, 10, id - 1));
  TEST_ASSERT_TRUE(m.pending);
  TEST_ASSERT_FALSE(m.can_start(10));
  TEST_ASSERT_TRUE(m.accept(idle_status, false, 20, id));
  TEST_ASSERT_FALSE(m.pending);
  TEST_ASSERT_FALSE(m.can_start(20));
}
uint32_t fake_time = 100;
uint32_t clock_now() { return fake_time; }
struct FakeTransport : Transport {
  bool same_session = true;
  bool disconnect_during_poll = false;
  bool session_valid() const override { return same_session; }
  bool healthy = true;
  bool permission = true;
  bool receipt = true;
  uint32_t delay = 0;
  int polls = 0;
  int posts = 0;
  bool status(Status& out) override {
    ++polls;
    fake_time += delay;
    if (disconnect_during_poll) same_session = false;
    out.may_start = permission;
    return healthy;
  }
  bool post(Action) override { ++posts; return receipt; }
};
void action_preflight_and_no_retry() {
  fake_time = 100;
  FakeTransport t;
  t.healthy = false;
  TEST_ASSERT_FALSE(send_action(Action::Start, 100, clock_now, t));
  TEST_ASSERT_EQUAL(0, t.posts);
  t.healthy = true;
  t.permission = false;
  TEST_ASSERT_FALSE(send_action(Action::Start, 100, clock_now, t));
  TEST_ASSERT_EQUAL(0, t.posts);
  t.permission = true;
  t.receipt = false;
  TEST_ASSERT_FALSE(send_action(Action::Start, 100, clock_now, t));
  TEST_ASSERT_EQUAL(1, t.posts);  // Failed receipt does not trigger a retry.
  t.receipt = true;
  TEST_ASSERT_TRUE(send_action(Action::Drain, 100, clock_now, t));
  TEST_ASSERT_EQUAL(2, t.posts);
  TEST_ASSERT_EQUAL(3, t.polls);  // Drain does not depend on start permission.
}
void expired_requests_and_slow_preflight_do_not_post() {
  fake_time = 1100;
  FakeTransport t;
  TEST_ASSERT_FALSE(send_action(Action::Start, 100, clock_now, t));
  TEST_ASSERT_EQUAL(0, t.polls);
  fake_time = 100;
  t.delay = 3000;
  TEST_ASSERT_FALSE(send_action(Action::Start, 100, clock_now, t));
  TEST_ASSERT_EQUAL(0, t.posts);
  TEST_ASSERT_FALSE(send_action(Action::None, fake_time, clock_now, t));
}
void reconnect_invalidates_queued_and_inflight_intent() {
  fake_time = 100;
  FakeTransport queued;
  // Wi-Fi is currently healthy again, but the queued gesture belongs to
  // an earlier connection generation and is still younger than its TTL.
  queued.same_session = false;
  TEST_ASSERT_FALSE(send_action(Action::Start, 100, clock_now, queued));
  TEST_ASSERT_EQUAL(0, queued.polls);
  TEST_ASSERT_EQUAL(0, queued.posts);
  FakeTransport inflight;
  inflight.disconnect_during_poll = true;
  TEST_ASSERT_FALSE(send_action(Action::Start, 100, clock_now, inflight));
  TEST_ASSERT_EQUAL(1, inflight.polls);
  TEST_ASSERT_EQUAL(0, inflight.posts);
  TEST_ASSERT_FALSE(send_action(Action::Drain, 100, clock_now, inflight));
  TEST_ASSERT_EQUAL(0, inflight.posts);
}
#include "transport_cases.h"
#include "network_bench_cases.h"
#include "test_hub_contract.h"
void test_hub_requires_explicit_simulation_marker() {
  const char* valid = R"({"simulated":true})";
  TEST_ASSERT_TRUE(is_test_hub_response(valid, std::strlen(valid)));
  for (auto value : {"{}", "{", "null", R"({"simulated":false})",
                     R"({"simulated":"true"})", R"({"simulated":1})"})
    TEST_ASSERT_FALSE(is_test_hub_response(value, std::strlen(value)));
}
int main() {
  UNITY_BEGIN();
  RUN_TEST(test_hub_requires_explicit_simulation_marker);
  run_transport_tests();
  RUN_TEST(network_bench_requires_live_status_and_runs_once);
  RUN_TEST(network_bench_recovery_is_bounded_and_wrap_safe);
  RUN_TEST(network_bench_cannot_pass_without_loss_or_after_deadline);
  RUN_TEST(reconnect_invalidates_queued_and_inflight_intent);
  RUN_TEST(parses_hub_contract);
  RUN_TEST(rejects_bad_status_and_clears_old_permissions);
  RUN_TEST(safe_and_automatic_modes_cannot_start);
  RUN_TEST(weather_assisted_status_is_display_only);
  RUN_TEST(weather_assisted_accepts_hub_maximum_countdown);
  RUN_TEST(stale_pending_and_wraparound);
  RUN_TEST(gesture_requires_release_hold_and_one_action);
  RUN_TEST(gesture_cancels_on_move_disconnect_and_recovery);
  RUN_TEST(render_is_deferred_only_during_valid_start_hold);
  RUN_TEST(unsampled_gap_cannot_complete_hold);
  RUN_TEST(receipts_must_match_action);
  RUN_TEST(delayed_poll_cannot_clear_pending_action);
  RUN_TEST(action_preflight_and_no_retry);
  RUN_TEST(expired_requests_and_slow_preflight_do_not_post);
  return UNITY_END();
}
