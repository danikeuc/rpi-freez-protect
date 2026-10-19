#include "action.h"
namespace gen4 {
bool send_action(Action action, uint32_t created_ms,
                 uint32_t (*now)(), Transport& transport) {
  if ((action != Action::Start && action != Action::Drain) ||
      uint32_t(now() - created_ms) >= 1000 || !transport.session_valid()) return false;
  if (action == Action::Start) {
    Status current;
    if (!transport.status(current) || !current.may_start ||
        uint32_t(now() - created_ms) >= 3000) return false;
  }
  return transport.session_valid() && transport.post(action);
}
}
