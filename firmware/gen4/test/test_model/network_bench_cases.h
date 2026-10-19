#pragma once
#include "network_bench.h"

void network_bench_requires_live_status_and_runs_once() {
  NetworkBench bench;
  TEST_ASSERT_FALSE(bench.begin(10, false, true));
  TEST_ASSERT_FALSE(bench.begin(10, true, false));
  TEST_ASSERT_TRUE(bench.begin(10, true, true));
  bench.disconnected(true);
  TEST_ASSERT_FALSE(bench.begin(11, true, true));
  TEST_ASSERT_FALSE(bench.reconnect_due(30009, false, false));
  TEST_ASSERT_TRUE(bench.reconnect_due(30010, false, false));
  TEST_ASSERT_FALSE(bench.reconnect_due(30011, false, false));
  TEST_ASSERT_EQUAL_UINT(2, bench.phase());
  bench.reconnect_due(30100, true, false);
  TEST_ASSERT_EQUAL_UINT(2, bench.phase());
  bench.reconnect_due(30200, true, true);
  TEST_ASSERT_EQUAL_UINT(3, bench.phase());
  TEST_ASSERT_FALSE(bench.begin(30300, true, true));
  TEST_ASSERT_FALSE(bench.reconnect_due(90000, true, true));
}
void network_bench_cannot_pass_without_loss_or_after_deadline() {
  NetworkBench no_loss;
  TEST_ASSERT_TRUE(no_loss.begin(0, true, true));
  no_loss.disconnected(true);
  TEST_ASSERT_TRUE(no_loss.reconnect_due(30000, true, true));
  no_loss.reconnect_due(30001, true, true);
  TEST_ASSERT_EQUAL_UINT(4, no_loss.phase());
  NetworkBench late;
  TEST_ASSERT_TRUE(late.begin(0, true, true));
  late.disconnected(true);
  TEST_ASSERT_TRUE(late.reconnect_due(30000, false, false));
  late.reconnect_due(60000, true, true);
  TEST_ASSERT_EQUAL_UINT(4, late.phase());
  NetworkBench failed_request;
  TEST_ASSERT_TRUE(failed_request.begin(0, true, true));
  failed_request.disconnected(false);
  TEST_ASSERT_TRUE(failed_request.reconnect_due(30000, false, false));
  failed_request.reconnect_due(30001, true, true);
  TEST_ASSERT_EQUAL_UINT(4, failed_request.phase());
}
void network_bench_recovery_is_bounded_and_wrap_safe() {
  NetworkBench bench;
  const uint32_t start = 0xFFFFF000u;
  TEST_ASSERT_TRUE(bench.begin(start, true, true));
  TEST_ASSERT_FALSE(bench.reconnect_due(start + 29999u, false, false));
  TEST_ASSERT_TRUE(bench.reconnect_due(start + 30000u, false, false));
  bench.reconnect_due(start + 59999u, true, false);
  TEST_ASSERT_EQUAL_UINT(2, bench.phase());
  bench.reconnect_due(start + 60000u, true, false);
  TEST_ASSERT_EQUAL_UINT(4, bench.phase());
  bench.reconnect_due(start + 60001u, true, true);
  TEST_ASSERT_EQUAL_UINT(4, bench.phase());
  TEST_ASSERT_FALSE(bench.begin(start + 60002u, true, true));
}
