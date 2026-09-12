#pragma once

#include <string>

#include "display_types.h"

struct HubResult {
  bool connected = false;
  HubStatus status;
};

class HubClient {
 public:
  static constexpr const char* kStatusPath = "/api/v1/display/status";
  static constexpr const char* kTimedShowerPath =
      "/api/v1/display/actions/timed-shower";
  static constexpr const char* kDrainPath = "/api/v1/display/actions/drain";

  HubClient(std::string base_url, std::string display_token);

  HubResult poll();
  bool start_timed_shower();
  bool drain();

 private:
  std::string endpoint(const char* path) const;
  bool post(const char* path);

  std::string base_url_;
  std::string display_token_;
};
