#pragma once
#include "model.h"
namespace gen4 {
class Transport {
 public:
  virtual ~Transport() = default;
  virtual bool session_valid() const = 0;
  virtual bool status(Status& out) = 0;
  virtual bool post(Action action) = 0;
};
// One attempt, no retry or persistence. Caller must supply a new deliberate
// gesture for every call. The Hub remains the duration/idempotency authority.
bool send_action(Action action, uint32_t created_ms,
                 uint32_t (*now)(), Transport& transport);
}
