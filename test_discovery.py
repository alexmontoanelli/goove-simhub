import unittest

import discovery_dialog as dd


class TestMergeDevices(unittest.TestCase):
    def test_appends_new_unique(self):
        existing = [{"ip": "1.1.1.1"}]
        merged = dd.merge_devices(existing, [{"ip": "2.2.2.2"}])
        self.assertEqual([d["ip"] for d in merged], ["1.1.1.1", "2.2.2.2"])

    def test_dedups_by_ip_preserving_order(self):
        existing = [{"ip": "1.1.1.1", "sku": "old"}]
        merged = dd.merge_devices(existing, [{"ip": "1.1.1.1", "sku": "new"}])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["ip"], "1.1.1.1")
        self.assertEqual(merged[0]["sku"], "old")  # mantém o primeiro visto

    def test_ignores_entries_without_ip(self):
        merged = dd.merge_devices([], [{"sku": "x"}, {"ip": "3.3.3.3"}])
        self.assertEqual([d["ip"] for d in merged], ["3.3.3.3"])


if __name__ == "__main__":
    unittest.main()
