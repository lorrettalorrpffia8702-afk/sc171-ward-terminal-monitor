import os
import time
import csv
import json
import subprocess
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

TARGET_IP = "223.5.5.5"
LOG_FILE = "network_log.csv"
PORT = 5000

def run_cmd(cmd):
    try:
        result = subprocess.check_output(
            cmd,
            shell=True,
            stderr=subprocess.DEVNULL,
            timeout=3
        )
        return result.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""

def get_ip():
    ip = run_cmd("hostname -I")
    if ip:
        return ip.split()[0]
    return "unknown"

def get_cpu_usage():
    try:
        def read_cpu():
            with open("/proc/stat", "r") as f:
                data = f.readline().split()[1:]
            data = list(map(int, data))
            idle = data[3] + data[4]
            total = sum(data)
            return idle, total

        idle1, total1 = read_cpu()
        time.sleep(0.1)
        idle2, total2 = read_cpu()

        idle_delta = idle2 - idle1
        total_delta = total2 - total1

        if total_delta == 0:
            return 0.0

        usage = 100 * (1 - idle_delta / total_delta)
        return round(usage, 1)
    except Exception:
        return 0.0

def get_memory_usage():
    try:
        meminfo = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                key, value = line.split(":", 1)
                meminfo[key] = int(value.strip().split()[0])

        total = meminfo.get("MemTotal", 1)
        available = meminfo.get("MemAvailable", 0)
        used = total - available

        return round(used / total * 100, 1)
    except Exception:
        return 0.0

def get_temperature():
    try:
        base = "/sys/class/thermal"
        temps = []

        for name in os.listdir(base):
            if name.startswith("thermal_zone"):
                path = os.path.join(base, name, "temp")
                if os.path.exists(path):
                    with open(path, "r") as f:
                        value = f.read().strip()

                    if value.isdigit():
                        temp = int(value)
                        if temp > 1000:
                            temp = temp / 1000.0
                        if 0 < temp < 120:
                            temps.append(temp)

        if not temps:
            return None

        return round(max(temps), 1)
    except Exception:
        return None

def get_net_bytes():
    rx_total = 0
    tx_total = 0

    try:
        with open("/proc/net/dev", "r") as f:
            lines = f.readlines()[2:]

        for line in lines:
            if ":" not in line:
                continue

            iface, data = line.split(":", 1)
            iface = iface.strip()

            if iface == "lo":
                continue

            fields = data.split()
            rx_total += int(fields[0])
            tx_total += int(fields[8])

        return rx_total, tx_total
    except Exception:
        return 0, 0

LAST_TIME = time.time()
LAST_RX, LAST_TX = get_net_bytes()

def get_net_speed():
    global LAST_TIME, LAST_RX, LAST_TX

    now = time.time()
    rx, tx = get_net_bytes()

    dt = now - LAST_TIME
    if dt <= 0:
        return 0.0, 0.0

    rx_speed = (rx - LAST_RX) / dt / 1024
    tx_speed = (tx - LAST_TX) / dt / 1024

    LAST_TIME = now
    LAST_RX = rx
    LAST_TX = tx

    return round(max(rx_speed, 0), 2), round(max(tx_speed, 0), 2)

def get_latency():
    output = run_cmd("ping -c 1 -W 1 {}".format(TARGET_IP))

    if "time=" not in output:
        return None

    try:
        value = output.split("time=")[1].split(" ")[0]
        return round(float(value), 2)
    except Exception:
        return None

def judge_status(latency, cpu, mem, temp):
    if latency is None:
        return "异常", "网络不可达"

    if latency > 200 or cpu > 90 or mem > 90 or (temp is not None and temp > 80):
        return "异常", "网络延迟过高或系统负载过高"

    if latency > 80 or cpu > 70 or mem > 75 or (temp is not None and temp > 65):
        return "一般", "网络或系统状态一般"

    return "正常", "网络与系统运行稳定"

def write_log(data):
    file_exists = os.path.exists(LOG_FILE)

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "time",
            "ip",
            "latency_ms",
            "rx_kbps",
            "tx_kbps",
            "cpu_percent",
            "memory_percent",
            "temperature",
            "status",
            "message"
        ])

        if not file_exists:
            writer.writeheader()

        writer.writerow(data)

def get_status_data():
    ip = get_ip()
    latency = get_latency()
    cpu = get_cpu_usage()
    mem = get_memory_usage()
    temp = get_temperature()
    rx_speed, tx_speed = get_net_speed()
    status, message = judge_status(latency, cpu, mem, temp)

    data = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ip": ip,
        "latency_ms": latency,
        "rx_kbps": rx_speed,
        "tx_kbps": tx_speed,
        "cpu_percent": cpu,
        "memory_percent": mem,
        "temperature": temp,
        "status": status,
        "message": message,
        "target": TARGET_IP
    }

    write_log(data)
    return data

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>SC171 网络质量监测终端</title>
    <style>
        body {
            font-family: Arial, "Microsoft YaHei", sans-serif;
            background: #f1f3f6;
            padding: 30px;
        }
        h1 {
            text-align: center;
            margin-bottom: 8px;
        }
        .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 25px;
        }
        .status {
            max-width: 900px;
            margin: 20px auto;
            padding: 25px;
            border-radius: 16px;
            color: white;
            font-size: 28px;
            text-align: center;
        }
        .normal { background: #2ecc71; }
        .warn { background: #f39c12; }
        .danger { background: #e74c3c; }
        .grid {
            max-width: 900px;
            margin: auto;
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
        }
        .card {
            background: white;
            border-radius: 14px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .label {
            color: #666;
            font-size: 15px;
        }
        .value {
            margin-top: 10px;
            font-size: 26px;
            font-weight: bold;
        }
        .footer {
            max-width: 900px;
            margin: 25px auto;
            color: #777;
            text-align: center;
        }
    </style>
</head>
<body>
    <h1>基于广和通 SC171 的网络质量监测终端</h1>
    <div class="subtitle">实时监测网络延迟、上下行速率、CPU、内存和温度状态</div>

    <div id="statusBox" class="status normal">状态读取中...</div>

    <div class="grid">
        <div class="card">
            <div class="label">本机 IP</div>
            <div id="ip" class="value">--</div>
        </div>
        <div class="card">
            <div class="label">网络延迟</div>
            <div id="latency" class="value">--</div>
        </div>
        <div class="card">
            <div class="label">下载速率</div>
            <div id="rx" class="value">--</div>
        </div>
        <div class="card">
            <div class="label">上传速率</div>
            <div id="tx" class="value">--</div>
        </div>
        <div class="card">
            <div class="label">CPU 占用</div>
            <div id="cpu" class="value">--</div>
        </div>
        <div class="card">
            <div class="label">内存占用</div>
            <div id="mem" class="value">--</div>
        </div>
        <div class="card">
            <div class="label">CPU 温度</div>
            <div id="temp" class="value">--</div>
        </div>
        <div class="card">
            <div class="label">检测目标</div>
            <div id="target" class="value">--</div>
        </div>
        <div class="card">
            <div class="label">更新时间</div>
            <div id="time" class="value">--</div>
        </div>
    </div>

    <div class="footer">数据自动记录到 network_log.csv，可用于后续展示和分析。</div>

<script>
async function updateData() {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();

        document.getElementById("ip").innerText = data.ip;
        document.getElementById("latency").innerText = data.latency_ms === null ? "超时" : data.latency_ms + " ms";
        document.getElementById("rx").innerText = data.rx_kbps + " KB/s";
        document.getElementById("tx").innerText = data.tx_kbps + " KB/s";
        document.getElementById("cpu").innerText = data.cpu_percent + " %";
        document.getElementById("mem").innerText = data.memory_percent + " %";
        document.getElementById("temp").innerText = data.temperature === null ? "未知" : data.temperature + " ℃";
        document.getElementById("target").innerText = data.target;
        document.getElementById("time").innerText = data.time;

        const box = document.getElementById("statusBox");
        box.className = "status";

        if (data.status === "正常") {
            box.classList.add("normal");
        } else if (data.status === "一般") {
            box.classList.add("warn");
        } else {
            box.classList.add("danger");
        }

        box.innerText = data.status + "：" + data.message;
    } catch (e) {
        const box = document.getElementById("statusBox");
        box.className = "status danger";
        box.innerText = "异常：网页无法读取终端数据";
    }
}

setInterval(updateData, 1000);
updateData();
</script>
</body>
</html>
"""

class MonitorHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            content = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif self.path.startswith("/api/status"):
            data = get_status_data()
            content = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        else:
            content = "404 Not Found".encode("utf-8")
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    def log_message(self, format, *args):
        return

if __name__ == "__main__":
    ip = get_ip()
    print("SC171 网络质量监测终端启动中...")
    print("本机 IP:", ip)
    print("板子本机访问: http://127.0.0.1:{}".format(PORT))
    print("局域网访问:   http://{}:{}".format(ip, PORT))
    print("按 Ctrl + C 停止程序")

    server = HTTPServer(("0.0.0.0", PORT), MonitorHandler)
    server.serve_forever()
PY
