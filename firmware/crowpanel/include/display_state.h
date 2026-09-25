#pragma once

#include "display_types.h"

DisplayModel reduce_status(const HubStatus& status, bool wifi_connected,
                           bool hub_connected);
std::string connection_diagnostic(bool wifi_connected, bool hub_connected,
                                  int http_status, int wifi_status);
std::string wifi_diagnostic_details(int wifi_status, const std::string& ip,
                                    const std::string& mac,
                                    int disconnect_reason, int http_status,
                                    bool last_payload_valid,
                                    unsigned long last_poll_age_s,
                                    bool has_last_poll);
DisplayAction next_action(const DisplayModel& model);
DisplayInteraction primary_press(DisplayPage page, const DisplayModel& model);
DisplayPage move_page(DisplayPage current, bool forward);
std::string home_state_label(const DisplayModel& model);
