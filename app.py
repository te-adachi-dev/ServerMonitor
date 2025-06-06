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
        'network': get_network_info()
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

# テンプレートを作成
with open(os.path.join(os.path.dirname(__file__), 'templates', 'index.html'), 'w') as f:
    f.write("""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>サーバー監視ダッシュボード</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.0/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.7.0/jquery.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.0/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
    <style>
        body {
            padding-top: 20px;
            background-color: #f5f5f5;
        }
        .card {
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .card-header {
            font-weight: bold;
            background-color: #f8f9fa;
        }
        .progress {
            height: 25px;
            margin-bottom: 10px;
        }
        .progress-bar {
            font-weight: bold;
        }
        .gauge {
            height: 200px;
        }
        .table-responsive {
            max-height: 300px;
            overflow-y: auto;
        }
        .refresh-btn {
            margin-bottom: 20px;
        }
        #system-info {
            font-size: 14px;
        }
        #last-update {
            font-style: italic;
            text-align: right;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="text-center mb-4">サーバー監視ダッシュボード</h1>
        
        <div class="d-flex justify-content-between align-items-center mb-3">
            <button id="refresh-btn" class="btn btn-primary"><i class="fas fa-sync-alt"></i> 更新</button>
            <div id="last-update">最終更新: -</div>
        </div>
        
        <!-- システム情報 -->
        <div class="card">
            <div class="card-header">
                <i class="fas fa-server"></i> システム情報
            </div>
            <div class="card-body">
                <div class="row" id="system-info">
                    <!-- ここにシステム情報が動的に追加されます -->
                </div>
            </div>
        </div>
        
        <div class="row">
            <!-- CPU情報 -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-microchip"></i> CPU使用率
                    </div>
                    <div class="card-body">
                        <div id="cpu-model" class="mb-2"></div>
                        <div class="progress mb-3">
                            <div id="cpu-usage" class="progress-bar" role="progressbar" style="width: 0%;" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">0%</div>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <div id="cpu-info"></div>
                            </div>
                            <div class="col-md-6">
                                <canvas id="cpu-chart" height="200"></canvas>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- メモリ情報 -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-memory"></i> メモリ使用率
                    </div>
                    <div class="card-body">
                        <div class="progress mb-3">
                            <div id="memory-usage" class="progress-bar" role="progressbar" style="width: 0%;" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">0%</div>
                        </div>
                        <div id="memory-info"></div>
                        <div class="mt-3">
                            <h6>スワップ</h6>
                            <div class="progress">
                                <div id="swap-usage" class="progress-bar bg-info" role="progressbar" style="width: 0%;" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">0%</div>
                            </div>
                            <div id="swap-info"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="row">
            <!-- 温度情報 -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-thermometer-half"></i> 温度情報
                    </div>
                    <div class="card-body">
                        <div id="temperature-info">
                            <!-- ここに温度情報が動的に追加されます -->
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- GPU情報 -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <i class="fas fa-tv"></i> GPU情報
                    </div>
                    <div class="card-body" id="gpu-info">
                        <!-- ここにGPU情報が動的に追加されます -->
                    </div>
                </div>
            </div>
        </div>
        
        <!-- ディスク情報 -->
        <div class="card">
            <div class="card-header">
                <i class="fas fa-hdd"></i> ディスク使用率
            </div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-striped">
                        <thead>
                            <tr>
                                <th>マウントポイント</th>
                                <th>デバイス</th>
                                <th>ファイルシステム</th>
                                <th>合計</th>
                                <th>使用中</th>
                                <th>空き</th>
                                <th>使用率</th>
                            </tr>
                        </thead>
                        <tbody id="disk-info">
                            <!-- ここにディスク情報が動的に追加されます -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <!-- ネットワーク情報 -->
        <div class="card">
            <div class="card-header">
                <i class="fas fa-network-wired"></i> ネットワーク情報
            </div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-striped">
                        <thead>
                            <tr>
                                <th>インターフェース</th>
                                <th>IPアドレス</th>
                                <th>送信 (MB)</th>
                                <th>受信 (MB)</th>
                            </tr>
                        </thead>
                        <tbody id="network-info">
                            <!-- ここにネットワーク情報が動的に追加されます -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script>
        // CPU履歴データ用の配列
        const cpuHistory = Array(20).fill(0);
        let cpuChart;
        
        // ページロード時に初期化
        $(document).ready(function() {
            // CPUグラフの初期化
            const cpuCtx = document.getElementById('cpu-chart').getContext('2d');
            cpuChart = new Chart(cpuCtx, {
                type: 'line',
                data: {
                    labels: Array(20).fill(''),
                    datasets: [{
                        label: 'CPU使用率 %',
                        data: cpuHistory,
                        borderColor: 'rgba(54, 162, 235, 1)',
                        backgroundColor: 'rgba(54, 162, 235, 0.2)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: 100
                        }
                    },
                    animation: {
                        duration: 0
                    }
                }
            });
            
            // 初回データ取得
            fetchAllData();
            
            // 更新ボタンのクリックイベント
            $('#refresh-btn').click(function() {
                fetchAllData();
            });
            
            // 定期的な更新（5秒ごと）
            setInterval(fetchAllData, 5000);
        });
        
        // すべてのデータを取得して表示
        function fetchAllData() {
            $.ajax({
                url: '/api/all',
                type: 'GET',
                dataType: 'json',
                success: function(data) {
                    // 最終更新時刻を更新
                    $('#last-update').text('最終更新: ' + data.timestamp);
                    
                    // システム情報を更新
                    updateSystemInfo(data.system);
                    
                    // CPU情報を更新
                    updateCpuInfo(data.cpu);
                    
                    // メモリ情報を更新
                    updateMemoryInfo(data.memory);
                    
                    // ディスク情報を更新
                    updateDiskInfo(data.disk);
                    
                    // 温度情報を更新
                    updateTemperatureInfo(data.temperature);
                    
                    // GPU情報を更新
                    updateGpuInfo(data.gpu);
                    
                    // ネットワーク情報を更新
                    updateNetworkInfo(data.network);
                },
                error: function(xhr, status, error) {
                    console.error('データ取得エラー:', error);
                }
            });
        }
        
        // システム情報を更新
        function updateSystemInfo(data) {
            const systemInfoHtml = `
                <div class="col-md-3 mb-2"><strong>ホスト名:</strong> ${data.hostname}</div>
                <div class="col-md-3 mb-2"><strong>OS:</strong> ${data.os} ${data.os_release}</div>
                <div class="col-md-3 mb-2"><strong>アーキテクチャ:</strong> ${data.architecture}</div>
                <div class="col-md-3 mb-2"><strong>起動時間:</strong> ${data.boot_time}</div>
                <div class="col-md-3 mb-2"><strong>稼働時間:</strong> ${data.uptime}</div>
            `;
            $('#system-info').html(systemInfoHtml);
        }
        
        // CPU情報を更新
        function updateCpuInfo(data) {
            // CPU使用率の更新
            $('#cpu-usage').css('width', data.usage_percent + '%');
            $('#cpu-usage').attr('aria-valuenow', data.usage_percent);
            $('#cpu-usage').text(data.usage_percent + '%');
            
            // CPU使用率の履歴を更新
            cpuHistory.push(data.usage_percent);
            cpuHistory.shift();
            cpuChart.data.datasets[0].data = cpuHistory;
            cpuChart.update();
            
            // CPUモデル情報
            $('#cpu-model').html(`<strong>${data.model}</strong>`);
            
            // CPU詳細情報
            const cpuInfoHtml = `
                <p><strong>物理コア数:</strong> ${data.cores}</p>
                <p><strong>スレッド数:</strong> ${data.threads}</p>
                <p><strong>現在の周波数:</strong> ${data.frequency} MHz</p>
            `;
            $('#cpu-info').html(cpuInfoHtml);
        }
        
        // メモリ情報を更新
        function updateMemoryInfo(data) {
            // メモリ使用率の更新
            $('#memory-usage').css('width', data.percent + '%');
            $('#memory-usage').attr('aria-valuenow', data.percent);
            $('#memory-usage').text(data.percent + '%');
            
            // メモリ詳細情報
            const memoryInfoHtml = `
                <p><strong>合計:</strong> ${data.total} GB</p>
                <p><strong>使用中:</strong> ${data.used} GB</p>
                <p><strong>空き:</strong> ${data.free} GB</p>
            `;
            $('#memory-info').html(memoryInfoHtml);
            
            // スワップ使用率の更新
            $('#swap-usage').css('width', data.swap_percent + '%');
            $('#swap-usage').attr('aria-valuenow', data.swap_percent);
            $('#swap-usage').text(data.swap_percent + '%');
            
            // スワップ詳細情報
            const swapInfoHtml = `
                <p><strong>合計:</strong> ${data.swap_total} GB</p>
                <p><strong>使用中:</strong> ${data.swap_used} GB</p>
                <p><strong>空き:</strong> ${data.swap_free} GB</p>
            `;
            $('#swap-info').html(swapInfoHtml);
        }
        
        // ディスク情報を更新
        function updateDiskInfo(data) {
            let diskInfoHtml = '';
            
            data.forEach(function(disk) {
                diskInfoHtml += `
                    <tr>
                        <td>${disk.mountpoint}</td>
                        <td>${disk.device}</td>
                        <td>${disk.fstype}</td>
                        <td>${disk.total} GB</td>
                        <td>${disk.used} GB</td>
                        <td>${disk.free} GB</td>
                        <td>
                            <div class="progress" style="height: 20px;">
                                <div class="progress-bar ${getDiskProgressBarClass(disk.percent)}" role="progressbar" style="width: ${disk.percent}%;" aria-valuenow="${disk.percent}" aria-valuemin="0" aria-valuemax="100">${disk.percent}%</div>
                            </div>
                        </td>
                    </tr>
                `;
            });
            
            $('#disk-info').html(diskInfoHtml);
        }
        
        // ディスク使用率に応じてプログレスバーの色を変更
        function getDiskProgressBarClass(percent) {
            if (percent >= 90) {
                return 'bg-danger';
            } else if (percent >= 70) {
                return 'bg-warning';
            } else {
                return 'bg-success';
            }
        }
        
        // 温度情報を更新
        function updateTemperatureInfo(data) {
            let tempInfoHtml = '';
            
            if (data.error) {
                tempInfoHtml = `<p class="text-warning">注意: ${data.error}</p>`;
            } else {
                if (data.cpu) {
                    tempInfoHtml += '<div class="mb-3"><h5>CPU温度</h5>';
                    for (const [key, value] of Object.entries(data.cpu)) {
                        tempInfoHtml += `
                            <div class="mb-2">
                                <div class="d-flex justify-content-between align-items-center">
                                    <span>${key}:</span>
                                    <span class="${getTemperatureClass(value)}">${value}°C</span>
                                </div>
                                <div class="progress" style="height: 15px;">
                                    <div class="progress-bar ${getTemperatureProgressBarClass(value)}" role="progressbar" style="width: ${Math.min(value * 100 / 100, 100)}%;" aria-valuenow="${value}" aria-valuemin="0" aria-valuemax="100"></div>
                                </div>
                            </div>
                        `;
                    }
                    tempInfoHtml += '</div>';
                }
                
                if (data.nvme) {
                    tempInfoHtml += '<div><h5>ストレージ温度</h5>';
                    for (const [key, value] of Object.entries(data.nvme)) {
                        tempInfoHtml += `
                            <div class="mb-2">
                                <div class="d-flex justify-content-between align-items-center">
                                    <span>${key}:</span>
                                    <span class="${getTemperatureClass(value)}">${value}°C</span>
                                </div>
                                <div class="progress" style="height: 15px;">
                                    <div class="progress-bar ${getTemperatureProgressBarClass(value)}" role="progressbar" style="width: ${Math.min(value * 100 / 100, 100)}%;" aria-valuenow="${value}" aria-valuemin="0" aria-valuemax="100"></div>
                                </div>
                            </div>
                        `;
                    }
                    tempInfoHtml += '</div>';
                }
            }
            
            $('#temperature-info').html(tempInfoHtml || '<p>温度情報は利用できません</p>');
        }
        
        // 温度に応じてテキスト色を変更
        function getTemperatureClass(value) {
            if (value >= 80) {
                return 'text-danger fw-bold';
            } else if (value >= 70) {
                return 'text-warning fw-bold';
            } else if (value >= 60) {
                return 'text-warning';
            } else {
                return 'text-success';
            }
        }
        
        // 温度に応じてプログレスバーの色を変更
        function getTemperatureProgressBarClass(value) {
            if (value >= 80) {
                return 'bg-danger';
            } else if (value >= 70) {
                return 'bg-warning';
            } else if (value >= 60) {
                return 'bg-info';
            } else {
                return 'bg-success';
            }
        }
        
        // GPU情報を更新
        function updateGpuInfo(data) {
            let gpuInfoHtml = '';
            
            if (data.error) {
                gpuInfoHtml = `<p class="text-danger">エラー: ${data.error}</p>`;
            } else {
                gpuInfoHtml = `
                    <p><strong>デバイス:</strong> ${data.device}</p>
                    <p><strong>ドライバ:</strong> ${data.driver}</p>
                `;
            }
            
            $('#gpu-info').html(gpuInfoHtml);
        }
        
        // ネットワーク情報を更新
        function updateNetworkInfo(data) {
            let networkInfoHtml = '';
            
            if (data.error) {
                networkInfoHtml = `<tr><td colspan="4" class="text-danger">エラー: ${data.error}</td></tr>`;
            } else {
                for (const [nic, info] of Object.entries(data)) {
                    // IPv4アドレスを取得
                    let ipAddress = 'なし';
                    if (info.addresses && info.addresses.length > 0) {
                        for (const addr of info.addresses) {
                            if (addr.type === 'AF_INET') {
                                ipAddress = addr.address;
                                break;
                            }
                        }
                    }
                    
                    networkInfoHtml += `
                        <tr>
                            <td>${nic}</td>
                            <td>${ipAddress}</td>
                            <td>${info.sent}</td>
                            <td>${info.received}</td>
                        </tr>
                    `;
                }
            }
            
            $('#network-info').html(networkInfoHtml);
        }
    </script>
</body>
</html>
    """)

# メインエントリポイント
if __name__ == '__main__':
    # 0.0.0.0でリッスンすることで外部からアクセス可能にする
    app.run(host='0.0.0.0', port=5000, debug=True)
