#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <cctype>

namespace gen4 {
constexpr uint32_t kExchangeMs = 2000;
// Io.connect(timeout), send/read (nonblocking; -1 pending, -2 error/EOF),
// now(), idle(), stop(). No redirects, chunking, reconnects or POST retries.
template<class Io> bool http_exchange(Io& io, const char* request,
    char* body, std::size_t capacity, std::size_t& body_size, uint32_t& started) {
  started = io.now();
  body_size = 0;
  struct Close { Io& io; ~Close() { io.stop(); } } close{io};
  const auto expired = [&]() { return uint32_t(io.now() - started) >= kExchangeMs; };
  if (!io.connect(1000) || expired()) return false;
  std::size_t sent = 0;
  const std::size_t request_size = std::strlen(request);
  while (sent < request_size) {
    if (expired()) return false;
    const int n = io.send(request + sent, request_size - sent);
    if (n == -2 || n > int(request_size - sent)) return false;
    if (n > 0) sent += std::size_t(n);
    else io.idle();
  }
  const auto byte = [&]() -> int {
    while (!expired()) {
      const int value = io.read();
      if (value != -1) return value;
      io.idle();
    }
    return -2;
  };
  char line[256];
  std::size_t header_bytes = 0;
  const auto get_line = [&]() -> bool {
    std::size_t used = 0;
    for (;;) {
      const int c = byte();
      if (c < 0 || ++header_bytes > 2048) return false;
      if (c == '\r') {
        if (byte() != '\n' || ++header_bytes > 2048) return false;
        line[used] = 0;
        return true;
      }
      if (c < 32 || c > 126 || used >= sizeof(line) - 1) return false;
      line[used++] = char(c);
    }
  };
  if (!get_line() || std::strlen(line) < 12 ||
      (std::strncmp(line, "HTTP/1.0 200", 12) != 0 &&
       std::strncmp(line, "HTTP/1.1 200", 12) != 0) ||
      (line[12] != ' ' && line[12] != 0)) return false;
  bool have_length = false;
  std::size_t length = 0;
  for (;;) {
    if (!get_line()) return false;
    if (!line[0]) break;
    char* colon = std::strchr(line, ':');
    if (!colon || colon == line) return false;
    *colon = 0;
    for (char* p = line; *p; ++p) *p = char(std::tolower(static_cast<unsigned char>(*p)));
    if (std::strcmp(line, "transfer-encoding") == 0) return false;
    if (std::strcmp(line, "content-length") == 0) {
      if (have_length) return false;
      have_length = true;
      char* p = colon + 1;
      while (*p == ' ') ++p;
      if (*p < '0' || *p > '9') return false;
      while (*p >= '0' && *p <= '9') {
        length = length * 10 + unsigned(*p++ - '0');
        if (length > 4096 || length >= capacity) return false;
      }
      while (*p == ' ') ++p;
      if (*p || length == 0) return false;
    }
  }
  if (!have_length) return false;
  for (std::size_t i = 0; i < length; ++i) {
    const int c = byte();
    if (c < 0) return false;
    body[i] = char(c);
  }
  if (expired()) return false;
  body[length] = 0;
  body_size = length;
  return true;
}
}  // namespace gen4
