"""A test that fails for a reason outside the checkout: the check runs with no network."""

import socket
import unittest


class Environmental(unittest.TestCase):
    def test_the_provider_is_reachable(self):
        with socket.create_connection(("api.deepseek.com", 443), timeout=3):
            pass
