#pragma once
#if GEN4_TEST_HUB
#if !GEN4_TOUCH || GEN4_OFFLINE_BENCH || GEN4_NETWORK_BENCH
#error Test Hub requires the isolated CT test target
#endif
// Single reviewed workstation endpoint for this bounded bench session.
#define GEN4_TEST_HUB_URL "http://192.168.111.30:18081"
#undef HUB_BASE_URL
#undef DISPLAY_TOKEN
#define HUB_BASE_URL GEN4_TEST_HUB_URL
#define DISPLAY_TOKEN "gen4-bench-only"
#endif
