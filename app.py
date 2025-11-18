import os
import time
import json
import psutil
import subprocess
import socket
import re
from flask import Flask, render_template, jsonify
from datetime import datetime
import platform

app = Flask(__name__)

# テンプレートディレクトリを作成
os.makedirs(os.path.join(os.path.dirname(__file__), 'templates'), exist_ok=True)

# ローカルIPアドレスを取得する関数
def get_local_ip():
    try:
        # 複数の方法でIPアドレスを取得
        ip_addresses = []

        # 方法1: ネットワークインターフェースから取得
        net_addrs = psutil.net_if_addrs()
        for interface, addrs in net_addrs.items():
            # ループバックアドレス以外のインターフェースを確認
            if interface != 'lo' and not interface.startswith('docker'):
                for addr in addrs:
                    # IPv4アドレスのみを対象
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        # プライベートIPアドレスの範囲を確認
                        if (ip.startswith('192.168.') or
                            ip.startswith('10.') or
                            ip.startswith('172.')):
                            ip_addresses.append(ip)

        # 方法2: socketを使用したフォールバック
        if not ip_addresses:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip_addresses.append(s.getsockname()[0])
                s.close()
            except:
                pass

        return ip_addresses
    except Exception as e:
        print(f"IPアドレス取得エラー: {e}")
        return []

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

# nvidia-smiからGPU情報を取得
def get_nvidia_gpu_info():
    try:
        # nvidia-smiコマンドを実行
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,power.limit,fan.speed', 
             '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            gpu_info_list = []
            lines = result.stdout.strip().split('\n')
            
            for idx, line in enumerate(lines):
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 8:
                    gpu_info = {
                        'index': idx,
                        'name': parts[0],
                        'temperature': float(parts[1]) if parts[1] and parts[1] != '[N/A]' else None,
                        'utilization': float(parts[2]) if parts[2] and parts[2] != '[N/A]' else 0,
                        'memory_used': float(parts[3]) if parts[3] and parts[3] != '[N/A]' else 0,
                        'memory_total': float(parts[4]) if parts[4] and parts[4] != '[N/A]' else 0,
                        'power_draw': float(parts[5]) if parts[5] and parts[5] != '[N/A]' else 0,
                        'power_limit': float(parts[6]) if parts[6] and parts[6] != '[N/A]' else 0,
                        'fan_speed': float(parts[7]) if parts[7] and parts[7] != '[N/A]' else 0,
                        'type': 'nvidia'
                    }
                    
                    # メモリ使用率を計算
                    if gpu_info['memory_total'] > 0:
                        gpu_info['memory_percent'] = round((gpu_info['memory_used'] / gpu_info['memory_total']) * 100, 1)
                    else:
                        gpu_info['memory_percent'] = 0
                    
                    # 電力使用率を計算
                    if gpu_info['power_limit'] > 0:
                        gpu_info['power_percent'] = round((gpu_info['power_draw'] / gpu_info['power_limit']) * 100, 1)
                    else:
                        gpu_info['power_percent'] = 0
                    
                    gpu_info_list.append(gpu_info)
            
            return gpu_info_list if gpu_info_list else None
        
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return None

# 温度情報の取得
def get_temperature_info():
    try:
        temp_info = {}
        
        # CPU温度情報（既存のコード）
        try:
            output = subprocess.check_output(['sensors', '-j'], stderr=subprocess.DEVNULL, universal_newlines=True)
            sensors_data = json.loads(output)
            
            # CPUの温度情報
            if 'k10temp-pci-00c3' in sensors_data:
                temp_info['cpu'] = {}
                cpu_data = sensors_data['k10temp-pci-00c3']
                for key, value in cpu_data.items():
                    if key not in ['Adapter']:
                        if isinstance(value, dict) and any(k.endswith('_input') for k in value.keys()):
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
                            if isinstance(value, dict) and any(k.endswith('_input') for k in value.keys()):
                                for k, v in value.items():
                                    if k.endswith('_input') and isinstance(v, (int, float)):
                                        temp_info['nvme'][f"{key}"] = v
                                        break
        except:
            pass
        
        # GPU温度情報を追加
        gpu_info_list = get_nvidia_gpu_info()
        if gpu_info_list:
            temp_info['gpu'] = {}
            for gpu in gpu_info_list:
                if gpu['temperature'] is not None:
                    gpu_label = f"GPU{gpu['index']}"
                    if len(gpu_info_list) == 1:
                        gpu_label = "GPU"
                    temp_info['gpu'][gpu_label] = gpu['temperature']
        
        return temp_info
    except Exception as e:
        return {"error": str(e)}

# GPUの情報取得（拡張版）
def get_gpu_info():
    try:
        gpu_info = {}
        
        # nvidia-smiから詳細情報を取得
        nvidia_gpus = get_nvidia_gpu_info()
        
        if nvidia_gpus:
            gpu_info['gpus'] = nvidia_gpus
            gpu_info['driver'] = 'NVIDIA proprietary driver'
            gpu_info['available'] = True
        else:
            # nvidia-smiが使えない場合、lspciから基本情報を取得
            try:
                output = subprocess.check_output('lspci | grep -i vga', shell=True, universal_newlines=True)
                gpu_info['device'] = output.strip()
                gpu_info['driver'] = 'Unknown'
                gpu_info['available'] = True
                
                # ドライバ情報を取得
                try:
                    driver_output = subprocess.check_output('lsmod | grep -E "nvidia|nouveau|amdgpu|radeon"', 
                                                           shell=True, stderr=subprocess.DEVNULL, universal_newlines=True)
                    
                    if 'nvidia' in driver_output:
                        gpu_info['driver'] = 'NVIDIA proprietary driver'
                    elif 'nouveau' in driver_output:
                        gpu_info['driver'] = 'Nouveau open source driver (NVIDIA)'
                    elif 'amdgpu' in driver_output:
                        gpu_info['driver'] = 'AMDGPU open source driver (AMD)'
                    elif 'radeon' in driver_output:
                        gpu_info['driver'] = 'Radeon open source driver (AMD)'
                except:
                    pass
                
                gpu_info['gpus'] = None
            except:
                gpu_info['available'] = False
                gpu_info['message'] = 'GPUが検出されませんでした'

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

# 消費電力情報の取得
def get_power_info():
    try:
        power_info = {
            'total_power': None,
            'gpu_power': [],
            'cpu_power': None,
            'amd_gpu': None
        }

        # NVIDIA GPU電力情報を取得
        gpu_info_list = get_nvidia_gpu_info()
        if gpu_info_list:
            for gpu in gpu_info_list:
                power_info['gpu_power'].append({
                    'name': gpu['name'],
                    'current': gpu['power_draw'],
                    'limit': gpu['power_limit'],
                    'percent': gpu['power_percent']
                })

        # AMD GPU電力情報を取得（amdgpu_pm_info経由）
        try:
            amd_power_path = '/sys/class/drm/card0/device/hwmon'
            if os.path.exists(amd_power_path):
                for hwmon_dir in os.listdir(amd_power_path):
                    power_file = os.path.join(amd_power_path, hwmon_dir, 'power1_average')
                    if os.path.exists(power_file):
                        with open(power_file, 'r') as f:
                            power_uw = int(f.read().strip())
                            power_w = power_uw / 1000000  # マイクロワットからワットへ
                            power_info['amd_gpu'] = {
                                'name': 'AMD GPU',
                                'current': round(power_w, 2),
                                'unit': 'W'
                            }
                        break
        except:
            pass

        # システム全体の電力を試行的に取得（RAPL経由など）
        try:
            # Linux RAPL (Running Average Power Limit) から電力情報を取得
            rapl_path = '/sys/class/powercap/intel-rapl'
            if os.path.exists(rapl_path):
                total_energy = 0
                for rapl_dir in os.listdir(rapl_path):
                    energy_file = os.path.join(rapl_path, rapl_dir, 'energy_uj')
                    if os.path.exists(energy_file):
                        with open(energy_file, 'r') as f:
                            energy_uj = int(f.read().strip())
                            total_energy += energy_uj
                power_info['cpu_power'] = 'RAPL available'
        except:
            pass

        # 合計電力を計算
        total = 0
        if power_info['gpu_power']:
            total += sum([g['current'] for g in power_info['gpu_power']])
        if power_info['amd_gpu']:
            total += power_info['amd_gpu']['current']

        if total > 0:
            power_info['total_power'] = round(total, 2)

        return power_info
    except Exception as e:
        return {"error": str(e)}

# 使用中のポート情報を取得
def get_port_info():
    try:
        port_info = []
        connections = psutil.net_connections(kind='inet')

        # ポートごとにプロセス情報を集約
        port_map = {}
        for conn in connections:
            if conn.status == 'LISTEN' and conn.laddr:
                port = conn.laddr.port
                if port not in port_map:
                    try:
                        if conn.pid:
                            proc = psutil.Process(conn.pid)
                            port_map[port] = {
                                'port': port,
                                'pid': conn.pid,
                                'process': proc.name(),
                                'user': proc.username(),
                                'status': conn.status,
                                'address': conn.laddr.ip if conn.laddr else 'N/A'
                            }
                        else:
                            port_map[port] = {
                                'port': port,
                                'pid': None,
                                'process': 'N/A',
                                'user': 'N/A',
                                'status': conn.status,
                                'address': conn.laddr.ip if conn.laddr else 'N/A'
                            }
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        port_map[port] = {
                            'port': port,
                            'pid': conn.pid,
                            'process': 'Access Denied',
                            'user': 'N/A',
                            'status': conn.status,
                            'address': conn.laddr.ip if conn.laddr else 'N/A'
                        }

        # リストに変換してポート番号でソート
        port_info = sorted(port_map.values(), key=lambda x: x['port'])
        return port_info
    except Exception as e:
        return {"error": str(e)}

# システムアラート情報を取得
def get_system_alerts():
    try:
        alerts = []

        # CPU使用率チェック
        cpu_percent = psutil.cpu_percent(interval=0.5)
        if cpu_percent > 90:
            alerts.append({
                'level': 'danger',
                'type': 'CPU',
                'message': f'CPU使用率が危険レベルです: {cpu_percent}%'
            })
        elif cpu_percent > 80:
            alerts.append({
                'level': 'warning',
                'type': 'CPU',
                'message': f'CPU使用率が高いです: {cpu_percent}%'
            })

        # メモリ使用率チェック
        memory = psutil.virtual_memory()
        if memory.percent > 90:
            alerts.append({
                'level': 'danger',
                'type': 'Memory',
                'message': f'メモリ使用率が危険レベルです: {memory.percent}%'
            })
        elif memory.percent > 80:
            alerts.append({
                'level': 'warning',
                'type': 'Memory',
                'message': f'メモリ使用率が高いです: {memory.percent}%'
            })

        # ディスク使用率チェック
        for partition in psutil.disk_partitions():
            try:
                if os.name == 'nt' and ('cdrom' in partition.opts or partition.fstype == ''):
                    continue
                # Snapパッケージは常に100%なので除外
                if partition.mountpoint.startswith('/snap/'):
                    continue
                # squashfsは読み取り専用のループデバイスなので除外
                if partition.fstype == 'squashfs':
                    continue
                usage = psutil.disk_usage(partition.mountpoint)
                if usage.percent > 90:
                    alerts.append({
                        'level': 'danger',
                        'type': 'Disk',
                        'message': f'{partition.mountpoint} のディスク使用率が危険レベルです: {usage.percent}%'
                    })
                elif usage.percent > 80:
                    alerts.append({
                        'level': 'warning',
                        'type': 'Disk',
                        'message': f'{partition.mountpoint} のディスク使用率が高いです: {usage.percent}%'
                    })
            except:
                pass

        # 温度チェック
        temp_info = get_temperature_info()
        if 'cpu' in temp_info:
            for key, value in temp_info['cpu'].items():
                if value > 85:
                    alerts.append({
                        'level': 'danger',
                        'type': 'Temperature',
                        'message': f'CPU温度が危険レベルです: {value}°C'
                    })
                elif value > 75:
                    alerts.append({
                        'level': 'warning',
                        'type': 'Temperature',
                        'message': f'CPU温度が高いです: {value}°C'
                    })

        return alerts
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
        'processes': get_process_info(),
        'power': get_power_info(),
        'ports': get_port_info(),
        'alerts': get_system_alerts()
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

# APIルート - 消費電力情報を取得
@app.route('/api/power')
def api_power():
    return jsonify(get_power_info())

# APIルート - ポート情報を取得
@app.route('/api/ports')
def api_ports():
    return jsonify(get_port_info())

# APIルート - システムアラート情報を取得
@app.route('/api/alerts')
def api_alerts():
    return jsonify(get_system_alerts())

# APIルート - プロセスをキル
@app.route('/api/kill_process/<int:pid>', methods=['POST'])
def api_kill_process(pid):
    try:
        proc = psutil.Process(pid)
        proc_name = proc.name()
        proc.terminate()  # まず丁寧に終了を試みる

        # 3秒待機して、まだ生きていたら強制終了
        try:
            proc.wait(timeout=3)
        except psutil.TimeoutExpired:
            proc.kill()

        return jsonify({
            'success': True,
            'message': f'プロセス {proc_name} (PID: {pid}) を終了しました'
        })
    except psutil.NoSuchProcess:
        return jsonify({
            'success': False,
            'message': f'PID {pid} のプロセスが見つかりません'
        }), 404
    except psutil.AccessDenied:
        return jsonify({
            'success': False,
            'message': f'PID {pid} のプロセスを終了する権限がありません'
        }), 403
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500

# APIルート - ポートを使用しているプロセスをキル
@app.route('/api/kill_port/<int:port>', methods=['POST'])
def api_kill_port(port):
    try:
        connections = psutil.net_connections(kind='inet')
        killed_processes = []

        for conn in connections:
            if conn.laddr and conn.laddr.port == port and conn.pid:
                try:
                    proc = psutil.Process(conn.pid)
                    proc_name = proc.name()
                    proc.terminate()

                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        proc.kill()

                    killed_processes.append(f'{proc_name} (PID: {conn.pid})')
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        if killed_processes:
            return jsonify({
                'success': True,
                'message': f'ポート {port} を使用していたプロセスを終了しました: {", ".join(killed_processes)}'
            })
        else:
            return jsonify({
                'success': False,
                'message': f'ポート {port} を使用しているプロセスが見つかりませんでした'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500

# メインエントリポイント
if __name__ == '__main__':
    # テンプレートディレクトリを作成
    os.makedirs(os.path.join(os.path.dirname(__file__), 'templates'), exist_ok=True)

    print('サーバー監視アプリを起動します...')

    # ローカルIPアドレスを取得
    local_ips = get_local_ip()

    print('以下のURLでアクセス可能です:')
    print('  http://localhost:5000')
    print('  http://127.0.0.1:5000')

    # 取得したIPアドレスを表示
    for ip in local_ips:
        print(f'  http://{ip}:5000')

    if not local_ips:
        print('警告: ローカルIPアドレスが取得できませんでした')

    # 0.0.0.0でリッスンすることで外部からアクセス可能にする
    app.run(host='0.0.0.0', port=5000, debug=True)
