import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../collector"))


class TestCollect(unittest.TestCase):

    def _make_mocks(self):
        ram  = MagicMock(percent=60.0, used=4 * 1024 ** 3)
        disk = MagicMock(percent=50.0, free=100 * 1024 ** 3)
        net  = MagicMock(bytes_sent=1024 ** 2, bytes_recv=2 * 1024 ** 2)
        return ram, disk, net

    @patch("psutil.cpu_percent", return_value=42.5)
    @patch("psutil.virtual_memory")
    @patch("psutil.disk_usage")
    @patch("psutil.net_io_counters")
    @patch("psutil.getloadavg", return_value=(1.2, 1.5, 1.8))
    def test_cpu_gauge_set(self, _load, mock_net, mock_disk, mock_ram, _cpu):
        ram, disk, net = self._make_mocks()
        mock_ram.return_value  = ram
        mock_disk.return_value = disk
        mock_net.return_value  = net
        import collector
        with patch.object(collector.cpu_usage, "set") as mock_set:
            collector.collect()
            mock_set.assert_called_once_with(42.5)

    @patch("psutil.cpu_percent", return_value=10.0)
    @patch("psutil.virtual_memory")
    @patch("psutil.disk_usage")
    @patch("psutil.net_io_counters")
    @patch("psutil.getloadavg", return_value=(0.5, 0.5, 0.5))
    def test_ram_gauge_set(self, _load, mock_net, mock_disk, mock_ram, _cpu):
        ram, disk, net = self._make_mocks()
        mock_ram.return_value  = ram
        mock_disk.return_value = disk
        mock_net.return_value  = net
        import collector
        with patch.object(collector.ram_usage, "set") as mock_set:
            collector.collect()
            mock_set.assert_called_once_with(60.0)

    @patch("psutil.cpu_percent", return_value=10.0)
    @patch("psutil.virtual_memory")
    @patch("psutil.disk_usage")
    @patch("psutil.net_io_counters")
    @patch("psutil.getloadavg", return_value=(0.5, 0.5, 0.5))
    def test_disk_gauge_set(self, _load, mock_net, mock_disk, mock_ram, _cpu):
        ram, disk, net = self._make_mocks()
        mock_ram.return_value  = ram
        mock_disk.return_value = disk
        mock_net.return_value  = net
        import collector
        with patch.object(collector.disk_usage, "set") as mock_set:
            collector.collect()
            mock_set.assert_called_once_with(50.0)

    @patch("psutil.cpu_percent", return_value=10.0)
    @patch("psutil.virtual_memory")
    @patch("psutil.disk_usage")
    @patch("psutil.net_io_counters")
    @patch("psutil.getloadavg", return_value=(1.2, 1.5, 1.8))
    def test_load_average_set(self, _load, mock_net, mock_disk, mock_ram, _cpu):
        ram, disk, net = self._make_mocks()
        mock_ram.return_value  = ram
        mock_disk.return_value = disk
        mock_net.return_value  = net
        import collector
        with patch.object(collector.load_1m, "set") as mock_set:
            collector.collect()
            mock_set.assert_called_once_with(1.2)

    @patch("psutil.cpu_percent", return_value=10.0)
    @patch("psutil.virtual_memory")
    @patch("psutil.disk_usage")
    @patch("psutil.net_io_counters")
    @patch("psutil.getloadavg", return_value=(0.5, 0.5, 0.5))
    def test_ram_gb_rounded(self, _load, mock_net, mock_disk, mock_ram, _cpu):
        ram  = MagicMock(percent=70.0, used=int(1.5 * 1024 ** 3))
        disk = MagicMock(percent=40.0, free=50 * 1024 ** 3)
        net  = MagicMock(bytes_sent=0, bytes_recv=0)
        mock_ram.return_value  = ram
        mock_disk.return_value = disk
        mock_net.return_value  = net
        import collector
        with patch.object(collector.ram_used_gb, "set") as mock_set:
            collector.collect()
            called_val = mock_set.call_args[0][0]
            self.assertAlmostEqual(called_val, 1.5, places=1)


if __name__ == "__main__":
    unittest.main()
