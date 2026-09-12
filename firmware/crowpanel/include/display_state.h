#pragma once

#include "display_types.h"

DisplayModel reduce_status(const HubStatus& status, bool wifi_connected,
                           bool hub_connected);
DisplayAction next_action(const DisplayModel& model);
DisplayPage move_page(DisplayPage current, bool forward);
