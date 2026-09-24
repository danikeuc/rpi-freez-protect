#pragma once

#include "display_types.h"

DisplayModel reduce_status(const HubStatus& status, bool wifi_connected,
                           bool hub_connected);
std::string connection_diagnostic(bool wifi_connected, bool hub_connected,
                                  int http_status, int wifi_status);
DisplayAction next_action(const DisplayModel& model);
DisplayInteraction primary_press(DisplayPage page, const DisplayModel& model);
DisplayPage move_page(DisplayPage current, bool forward);
std::string home_state_label(const DisplayModel& model);
