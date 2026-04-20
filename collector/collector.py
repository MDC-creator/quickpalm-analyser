import time
import psutil
from prometheus_client import start_http_server, Gauge

# Metrics
cpu_usage    = Gauge("node_cpu_percent",        "CPU usage in percent")
ram_usage    = Gauge("node_ram_percent",         "RAM usage in percent")
ram_used_gb  = Gauge("node_ram_used_gb",         "RAM used in GB")
disk_usage   = Gauge("node_disk_percent",        "Disk usage in percent")
disk_free_gb = Gauge("node_disk_free_gb",        "Disk free in GB")
net_sent_mb  = Gauge("node_net_sent_mb_total",   "Network bytes sent in MB")
net_recv_mb  = Gauge("node_net_recv_mb_total",   "Network bytes received in MB")
load_1m      = Gauge("node_load_1m",             "Load average 1 minute")
load_5m      = Gauge("node_load_5m",             "Load average 5 minutes")

INTERVAL = 5  # seconds

def collect():
    # CPU
    cpu_usage.set(psutil.cpu_percent(interval=1))

    # RAM
    ram = psutil.virtual_memory()
    ram_usage.set(ram.percent)
    ram_used_gb.set(round(ram.used / 1024**3, 2))

    # Disk
    disk = psutil.disk_usage("/")
    disk_usage.set(disk.percent)
    disk_free_gb.set(round(disk.free / 1024**3, 2))

    # Network
    net = psutil.net_io_counters()
    net_sent_mb.set(round(net.bytes_sent / 1024**2, 2))
    net_recv_mb.set(round(net.bytes_recv / 1024**2, 2))

    # Load average
    load = psutil.getloadavg()
    load_1m.set(load[0])
    load_5m.set(load[1])


if __name__ == "__main__":
    start_http_server(8000)
    print("Collector running on :8000 — metrics collected every 5s")
    while True:
        collect()
        time.sleep(INTERVAL)
