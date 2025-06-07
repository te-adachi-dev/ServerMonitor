import os
import time
import json
import psutil
import subprocess
from flask import Flask, render_template, jsonify
from datetime import datetime
import platform

app = Flask(__name__)

# テンプレートディレクトリを作成
os.makedirs(os.path.join(os.path.dirname(__file__), 'templates'), exist_ok=True)

# CPU情報の取得
def get_cpu_info():
    try:
        cpu_info = {}
        cpu_info['model'] = platform.processor()
        cpu_info['cores'] = psutil.cpu_count(logical=False)
        cpu_info['threads'] = psutil.cpu_count(logical=True)
        cpu_info['usage_percent'] = psutil.cpu_percent(interval=1)
        cpu_info['frequency'] = psutil.cpu_freq().current if psutil.cpu_freq() else "N/A"

        # 各コアの使用率
        cpu_info['per_core'] = psutil.cpu_percent(interval=0.1, percpu=True)

        return cpu_info
    except Exception as e:
        return {"error": str(e)}

# メモリ情報の取得
def get_memory_info():
    try:
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        memory_info = {
            'total': round(memory.total / (1024**3), 2),  # GB
            'used': round(memory.used / (1024**3), 2),    # GB
            'free': round(memory.available / (1024**3), 2),  # GB
            'percent': memory.percent,
            'swap_total': round(swap.total / (1024**3), 2),  # GB
            'swap_used': round(swap.used / (1024**3), 2),  # GB
            'swap_free': round(swap.free / (1024**3), 2),  # GB
            'swap_percent': swap.percent
        }

        return memory_info
    except Exception as e:
        return {"error": str(e)}

# ディスク情報の取得
def get_disk_info():
    try:
        disk_info = []
        for partition in psutil.disk_partitions():
            if os.name == 'nt' and ('cdrom' in partition.opts or partition.fstype == ''):
                continue
            usage = psutil.disk_usage(partition.mountpoint)
            disk_info.append({
                'device': partition.device,
                'mountpoint': partition.mountpoint,
                'fstype': partition.fstype,
                'total': round(usage.total / (1024**3), 2),  # GB
                'used': round(usage.used / (1024**3), 2),    # GB
                'free': round(usage.free / (1024**3), 2),    # GB
                'percent': usage.percent
            })

        return disk_info
    except Exception as e:
        return {"error": str(e)}

# 温度情報の取得
def get_temperature_info():
    try:
        # sensorsコマンドの出力を取得（エラー出力を破棄）
        try:
            output = subprocess.check_output(['sensors', '-j'], stderr=subprocess.DEVNULL, universal_newlines=True)
            sensors_data = json.loads(output)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            return {"error": "温度情報を取得できませんでした"}

        # 温度データを整形
        temp_info = {}

        # CPUの温度情報
        if 'k10temp-pci-00c3' in sensors_data:
            temp_info['cpu'] = {}
            cpu_data = sensors_data['k10temp-pci-00c3']
            for key, value in cpu_data.items():
                if key not in ['Adapter']:
                    # 値が辞書で、その中に温度値があるか確認
                    if isinstance(value, dict) and any(k.endswith('_input') for k in value.keys()):
                        # 最初の *_input 値を取得
                        for k, v in value.items():
                            if k.endswith('_input') and isinstance(v, (int, float)):
                                temp_info['cpu'][key] = v
                                break

        # NVMeの温度情報
        nvme_keys = [key for key in sensors_data.keys() if key.startswith('nvme')]
        if nvme_keys:
            temp_info['nvme'] = {}
            for nvme_key in nvme_keys:
                nvme_data = sensors_data[nvme_key]
                for key, value in nvme_data.items():
                    if key not in ['Adapter']:
                        # 値が辞書で、その中に温度値があるか確認
                        if isinstance(value, dict) and any(k.endswith('_input') for k in value.keys()):
                            # 最初の *_input 値を取得
                            for k, v in value.items():
                                if k.endswith('_input') and isinstance(v, (int, float)):
                                    temp_info['nvme'][f"{key}"] = v
                                    break

        return temp_info
    except Exception as e:
        return {"error": str(e)}

# GPUの情報取得
def get_gpu_info():
    try:
        # nvidiaの場合はnvidia-smi、AMDの場合はradeontopなどを使用
        # ここではlspciの出力を解析してGPU情報を表示
        output = subprocess.check_output('lspci | grep -i vga', shell=True, universal_newlines=True)

        gpu_info = {
            'device': output.strip(),
            'driver': 'Unknown'
        }

        # 可能であればドライバ情報も追加（glxinfoエラーを無視）
        try:
            driver_output = subprocess.check_output('lsmod | grep -E "nvidia|nouveau|amdgpu|radeon"', shell=True, stderr=subprocess.DEVNULL, universal_newlines=True)

            if 'nvidia' in driver_output:
                gpu_info['driver'] = 'NVIDIA proprietary driver'
            elif 'nouveau' in driver_output:
                gpu_info['driver'] = 'Nouveau open source driver (NVIDIA)'
            elif 'amdgpu' in driver_output:
                gpu_info['driver'] = 'AMDGPU open source driver (AMD)'
            elif 'radeon' in driver_output:
                gpu_info['driver'] = 'Radeon open source driver (AMD)'
        except:
            # ドライバ情報の取得に失敗した場合は無視
            pass

        return gpu_info
    except Exception as e:
        return {"error": str(e)}

# ネットワーク情報
def get_network_info():
    try:
        network_info = {}

        # ネットワークインターフェース情報
        net_io = psutil.net_io_counters(pernic=True)
        net_addrs = psutil.net_if_addrs()

        for nic, addrs in net_addrs.items():
            if nic in net_io:
                addr_info = []
                for addr in addrs:
                    addr_type = addr.family.name if hasattr(addr.family, 'name') else addr.family
                    addr_info.append({
                        'address': addr.address,
                        'netmask': addr.netmask,
                        'type': addr_type
                    })

                network_info[nic] = {
                    'addresses': addr_info,
                    'sent': round(net_io[nic].bytes_sent / (1024**2), 2),  # MB
                    'received': round(net_io[nic].bytes_recv / (1024**2), 2)  # MB
                }

        return network_info
    except Exception as e:
        return {"error": str(e)}

# システム情報
def get_system_info():
    try:
        uptime_seconds = time.time() - psutil.boot_time()
        days = int(uptime_seconds // (24 * 3600))
        hours = int((uptime_seconds % (24 * 3600)) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)

        system_info = {
            'hostname': platform.node(),
            'os': platform.system(),
            'os_release': platform.release(),
            'os_version': platform.version(),
            'architecture': platform.machine(),
            'uptime': f"{days}日 {hours}時間 {minutes}分",
            'boot_time': datetime.fromtimestamp(psutil.boot_time()).strftime('%Y-%m-%d %H:%M:%S')
        }

        return system_info
    except Exception as e:
        return {"error": str(e)}

# プロセス情報の取得
def get_process_info():
    try:
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_percent', 'cpu_percent']):
            try:
                pinfo = proc.info
                pinfo['memory_percent'] = round(pinfo['memory_percent'], 2)
                processes.append(pinfo)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        # CPU使用率でソート
        processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
        return processes[:20]  # 上位20プロセスだけ返す
    except Exception as e:
        return {"error": str(e)}

# すべての情報を取得
def get_all_info():
    return {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'system': get_system_info(),
        'cpu': get_cpu_info(),
        'memory': get_memory_info(),
        'disk': get_disk_info(),
        'temperature': get_temperature_info(),
        'gpu': get_gpu_info(),
        'network': get_network_info(),
        'processes': get_process_info()
    }

# ルートページ
@app.route('/')
def index():
    return render_template('index.html')

# APIルート - すべての情報を取得
@app.route('/api/all')
def api_all():
    return jsonify(get_all_info())

# APIルート - CPUの情報を取得
@app.route('/api/cpu')
def api_cpu():
    return jsonify(get_cpu_info())

# APIルート - メモリ情報を取得
@app.route('/api/memory')
def api_memory():
    return jsonify(get_memory_info())

# APIルート - ディスク情報を取得
@app.route('/api/disk')
def api_disk():
    return jsonify(get_disk_info())

# APIルート - 温度情報を取得
@app.route('/api/temperature')
def api_temperature():
    return jsonify(get_temperature_info())

# APIルート - GPU情報を取得
@app.route('/api/gpu')
def api_gpu():
    return jsonify(get_gpu_info())

# APIルート - ネットワーク情報を取得
@app.route('/api/network')
def api_network():
    return jsonify(get_network_info())

# APIルート - システム情報を取得
@app.route('/api/system')
def api_system():
    return jsonify(get_system_info())

# APIルート - プロセス情報を取得
@app.route('/api/processes')
def api_processes():
    return jsonify(get_process_info())

# メインエントリポイント
if __name__ == '__main__':
    # テンプレートディレクトリを作成
    os.makedirs(os.path.join(os.path.dirname(__file__), 'templates'), exist_ok=True)
    
    print('サーバー監視アプリを起動します...')
    print('ブラウザで http://localhost:5000 にアクセスしてください')
    
    # 0.0.0.0でリッスンすることで外部からアクセス可能にする
    app.run(host='0.0.0.0', port=5000, debug=True)
