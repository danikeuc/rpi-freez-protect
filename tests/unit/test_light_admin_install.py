import importlib.util
import unittest
import warnings
from pathlib import Path
from unittest.mock import Mock, patch

PATH = Path(__file__).parent / "install_admin.py"
if not PATH.exists():
    PATH = Path(__file__).parents[2] / "deployment/lighting/admin/install_admin.py"
spec = importlib.util.spec_from_file_location("light_admin_install", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class InstallerTests(unittest.TestCase):
    def test_gateway_is_additive_and_only_light_routes(self):
        config = m.gateway()
        self.assertIn("listen 192.168.114.192:8082;", config)
        self.assertIn("allow 192.168.114.173;", config)
        self.assertIn("deny all;", config)
        self.assertIn("access_log off;", config)
        self.assertNotIn("events/unifi", config)
        self.assertNotIn("/api/v1/display", config)
        self.assertEqual(config.count("proxy_pass http://127.0.0.1:8002;"), 4)
        self.assertEqual(config.count("location = /api/v1/lights/"), 4)

    def test_existing_connection_never_overwritten(self):
        for value in [{"configured": True, "generation": 2}, {},
                      {"configured": False, "generation": True},
                      {"configured": False, "generation": 1}]:
            with self.assertRaises(RuntimeError):
                m.guarded_config(value)
        m.guarded_config({"configured": False, "generation": 0})

    def test_redirects_never_forward_credentials(self):
        with self.assertRaisesRegex(RuntimeError, "HTTP_REDIRECT_REJECTED"):
            m.NoRedirect().redirect_request(None, None, 302, None, None, "http://evil/")

    def test_mutation_timeout_is_never_retried(self):
        client = Mock()
        client.open.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            m.request(client, "http://192.168.114.173/admin/api/light/config",
                      "PUT", {"display_token": "private"})
        self.assertEqual(client.open.call_count, 1)

    def test_http_failure_does_not_emit_body(self):
        client = Mock()
        response = Mock()
        response.status = 503
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        client.open.return_value = response
        with self.assertRaisesRegex(RuntimeError, "^HTTP_STATUS_503$"):
            m.request(client, "http://localhost/")
        response.read.assert_not_called()

    def test_no_pin_fallback_to_echo(self):
        with (patch.object(m.os, "isatty", return_value=False),
              self.assertRaisesRegex(RuntimeError, "PRIVATE_TERMINAL_REQUIRED")):
            m.private_pin()

    def test_pin_echo_fallback_aborts_before_read(self):
        def fallback(prompt):
            warnings.warn("fallback", m.getpass.GetPassWarning, stacklevel=1)
            raise AssertionError("PIN would be read with echo")
        with (patch.object(m.os, "isatty", return_value=True),
              patch.object(m.getpass, "getpass", side_effect=fallback),
              self.assertRaises(m.getpass.GetPassWarning)):
            m.private_pin()


if __name__ == "__main__":
    unittest.main()
