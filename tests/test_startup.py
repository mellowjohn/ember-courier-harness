"""The browser convenience must preserve a usable server when opening fails."""
from contextlib import redirect_stdout
import io
import unittest
from unittest.mock import Mock, patch

from ember_harness import local_ui


class StartupTests(unittest.TestCase):
    def start(self, arguments, *, browser_error=None):
        app = Mock(token='synthetic-private-token', session=None, stream=None)
        http = Mock(server_port=12345)
        http.serve_forever.side_effect = KeyboardInterrupt
        output = io.StringIO()
        with patch('sys.argv', ['ember-ui', *arguments]), patch.object(local_ui, 'App', return_value=app), \
                patch.object(local_ui, 'server', return_value=http), \
                patch('webbrowser.open', side_effect=browser_error) as browser, redirect_stdout(output):
            local_ui.main()
        http.serve_forever.assert_called_once()
        http.server_close.assert_called_once()
        return browser, output.getvalue()

    def test_explicit_browser_launch_uses_the_private_link(self):
        browser, output = self.start(['--open-browser'])
        browser.assert_called_once_with('http://127.0.0.1:12345/#synthetic-private-token')
        self.assertIn('Ember app:', output)

    def test_manual_launch_does_not_open_browser(self):
        browser, _ = self.start([])
        browser.assert_not_called()

    def test_browser_failure_leaves_server_and_printed_link_available(self):
        _, output = self.start(['--open-browser'], browser_error=OSError('synthetic missing browser'))
        self.assertIn('Open the private link above manually.', output)
        self.assertIn('http://127.0.0.1:12345/#synthetic-private-token', output)


if __name__ == '__main__':
    unittest.main()
