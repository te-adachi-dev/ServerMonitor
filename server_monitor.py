from flask import Flask, render_template, jsonify, request
import psutil
import platform
import datetime
import socket
import os
import time
import subprocess
import json
import threading
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# 設定
CONFIG_FILE = 'monitor_config.json'
DEFAULT_CONFIG = {
    'theme': 'light',
    'refresh_interval': 5,
    'last_server': '',
    'found_servers': []
}

# グローバル変数
config = DEFAULT_CONFIG.copy()
current_server = None
servers_lock = threading.Lock()
found_servers = []

def load_config():
    global config
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
    except Exception as e:
        print(f"設定ファイル読み込み中にエラーが発生しました: {e}")
        config = DEFAULT_CONFIG.copy()

def save_config():
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"設定ファイル保存中にエラーが発生しました: {e}")

def ping_host(ip):
    """指定されたIPアドレスにpingを実行し、応答があるか確認"""
    try:
        # Linuxコマンドでping
        output = subprocess.run(['ping', '-c', '1', '-W', '1', ip], 
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL, 
                               timeout=1.5)
        return output.returncode == 0
    except:
        return False

def get_hostname(ip):
    """IPアドレスからホスト名を取得試行"""
    try:
        return socket.gethostbyaddr(ip)[0]
    except:
        return ip

def scan_network():
    """ネットワークをスキャンして利用可能なLinuxサーバーを見つける"""
    global found_servers
    
    # 自分自身のIPアドレスを取得してネットワークプレフィックスを特定
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # この接続は実際には確立されない
        s.connect(('10.255.255.255', 1))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()
    
    # ネットワークプレフィックスを取得（例: 192.168.1）
    prefix = '.'.join(local_ip.split('.')[:3])
    
    # スキャン結果を一時的に保存
    temp_servers = []
    
    # 自分自身を追加
    temp_servers.append({
        'ip': local_ip,
        'hostname': socket.gethostname(),
        'is_local': True
    })
    
    # マルチスレッドでIPアドレスをスキャン
    def check_ip(i):
        ip = f"{prefix}.{i}"
        if ip != local_ip and ping_host(ip):
            hostname = get_hostname(ip)
            return {'ip': ip, 'hostname': hostname, 'is_local': False}
        return None
    
    # スレッドプールでIPをスキャン
    with ThreadPoolExecutor(max_workers=50) as executor:
        results = executor.map(check_ip, range(1, 255))
    
    # 結果をフィルタリング
    for result in results:
        if result:
            temp_servers.append(result)
    
    # グローバル変数を更新
    with servers_lock:
        found_servers = temp_servers
        config['found_servers'] = temp_servers
        save_config()
    
    return temp_servers

@app.route('/')
def index():
    global current_server
    
    # 現在のサーバーが設定されていない場合はローカルを使用
    if current_server is None:
        # 最後に使ったサーバーがあればそれを使用
        if config['last_server']:
            for server in found_servers:
                if server['ip'] == config['last_server']:
                    current_server = server
                    break
        
        # それでも見つからなければ自分自身を使用
        if current_server is None and found_servers:
            for server in found_servers:
                if server.get('is_local', False):
                    current_server = server
                    break
    
    # まだサーバーが見つからなければスキャンを開始
    if current_server is None:
        threading.Thread(target=scan_network).start()
    
    return render_template('index.html', config=config)

@app.route('/api/system_info')
def get_system_info():
    # システム情報
    system_info = {
        'hostname': socket.gethostname(),
        'platform': platform.platform(),
        'system': platform.system(),
        'release': platform.release(),
        'version': platform.version(),
        'processor': platform.processor(),
        'uptime': get_uptime(),
    }
    return jsonify(system_info)

@app.route('/api/resources')
def get_resources():
    # リソース情報（CPU、メモリ、ディスク）
    resources = {
        'cpu': {
            'percent': psutil.cpu_percent(interval=1),
            'count': psutil.cpu_count(),
            'freq': psutil.cpu_freq().current if psutil.cpu_freq() else 'N/A',
        },
        'memory': {
            'total': format_bytes(psutil.virtual_memory().total),
            'available': format_bytes(psutil.virtual_memory().available),
            'used': format_bytes(psutil.virtual_memory().used),
            'percent': psutil.virtual_memory().percent,
        },
        'disk': get_disk_info(),
        'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    return jsonify(resources)

@app.route('/api/processes')
def get_processes():
    # プロセス情報
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
    return jsonify(processes[:20])  # 上位20プロセスだけ返す

@app.route('/api/servers')
def get_servers():
    """見つかったサーバーのリストを返す"""
    with servers_lock:
        return jsonify(found_servers)

@app.route('/api/scan_servers', methods=['POST'])
def trigger_scan_servers():
    """サーバースキャンを開始"""
    threading.Thread(target=scan_network).start()
    return jsonify({'status': 'scanning'})

@app.route('/api/set_server', methods=['POST'])
def set_server():
    """監視対象サーバーを設定"""
    global current_server
    data = request.json
    ip = data.get('ip')
    
    with servers_lock:
        for server in found_servers:
            if server['ip'] == ip:
                current_server = server
                config['last_server'] = ip
                save_config()
                return jsonify({'status': 'success'})
    
    return jsonify({'status': 'error', 'message': '指定されたサーバーが見つかりません'})

@app.route('/api/set_theme', methods=['POST'])
def set_theme():
    """テーマを設定"""
    data = request.json
    theme = data.get('theme')
    
    if theme in ['light', 'dark']:
        config['theme'] = theme
        save_config()
        return jsonify({'status': 'success'})
    
    return jsonify({'status': 'error', 'message': '無効なテーマです'})

def get_uptime():
    # システム起動時間を計算
    uptime_seconds = int(time.time() - psutil.boot_time())
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}日 {hours}時間 {minutes}分 {seconds}秒"

def format_bytes(bytes):
    # バイト数を人間が読みやすい形式に変換
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.2f} PB"

def get_disk_info():
    # ディスク情報を取得
    disk_info = []
    for partition in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            disk_info.append({
                'device': partition.device,
                'mountpoint': partition.mountpoint,
                'fstype': partition.fstype,
                'total': format_bytes(usage.total),
                'used': format_bytes(usage.used),
                'free': format_bytes(usage.free),
                'percent': usage.percent
            })
        except (PermissionError, FileNotFoundError):
            # 一部のファイルシステムはエラーを起こすことがある
            pass
    return disk_info

if __name__ == '__main__':
    # 設定を読み込む
    load_config()
    
    # テンプレートディレクトリを作成
    os.makedirs('templates', exist_ok=True)
    
    # HTMLテンプレートを作成
    html_template = '''
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>サーバー監視ダッシュボード</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            padding: 20px;
            transition: background-color 0.3s, color 0.3s;
        }
        .card {
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: background-color 0.3s, color 0.3s;
        }
        .card-header {
            font-weight: bold;
            transition: background-color 0.3s, color 0.3s;
        }
        .progress {
            margin-top: 5px;
            height: 5px;
        }
        .table {
            font-size: 0.9rem;
            transition: background-color 0.3s, color 0.3s;
        }
        .refresh-time {
            font-size: 0.8rem;
            text-align: right;
            margin-bottom: 10px;
            transition: color 0.3s;
        }
        .bg-warning {
            background-color: #ffc107 !important;
        }
        .bg-danger {
            background-color: #dc3545 !important;
        }
        .server-selector {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 1000;
        }
        .theme-switch {
            position: fixed;
            top: 20px;
            right: 200px;
            z-index: 1000;
        }
        
        /* ダークテーマ用スタイル */
        body.dark-theme {
            background-color: #212529;
            color: #f8f9fa;
        }
        .dark-theme .card {
            background-color: #343a40;
            color: #f8f9fa;
        }
        .dark-theme .card-header {
            background-color: #2c3136;
            color: #f8f9fa;
        }
        .dark-theme .table {
            color: #f8f9fa;
        }
        .dark-theme .refresh-time {
            color: #adb5bd;
        }
        .dark-theme .dropdown-menu {
            background-color: #343a40;
            color: #f8f9fa;
        }
        .dark-theme .dropdown-item {
            color: #f8f9fa;
        }
        .dark-theme .dropdown-item:hover {
            background-color: #495057;
            color: #f8f9fa;
        }
        .dark-theme .btn-light {
            background-color: #495057;
            color: #f8f9fa;
            border-color: #6c757d;
        }
        .dark-theme .modal-content {
            background-color: #343a40;
            color: #f8f9fa;
        }
        .dark-theme hr {
            border-color: #6c757d;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="mb-4">サーバー監視ダッシュボード</h1>
        
        <!-- サーバー選択ドロップダウン -->
        <div class="server-selector">
            <div class="dropdown">
                <button class="btn btn-light dropdown-toggle" type="button" id="serverDropdown" data-bs-toggle="dropdown" aria-expanded="false">
                    サーバー選択
                </button>
                <ul class="dropdown-menu" id="server-list" aria-labelledby="serverDropdown">
                    <li><a class="dropdown-item" href="#" data-action="scan">ネットワークスキャン</a></li>
                    <li><hr class="dropdown-divider"></li>
                    <li><a class="dropdown-item" href="#" data-ip="loading">読み込み中...</a></li>
                </ul>
            </div>
        </div>
        
        <!-- テーマ切り替えボタン -->
        <div class="theme-switch">
            <button class="btn btn-light" id="theme-toggle">
                <span id="theme-icon">☀️</span> テーマ切替
            </button>
        </div>
        
        <div class="refresh-time">最終更新: <span id="refresh-time"></span></div>
        
        <div class="row">
            <!-- システム情報 -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">システム情報</div>
                    <div class="card-body">
                        <table class="table table-sm">
                            <tbody id="system-info">
                                <tr><td>読込中...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <!-- CPU & メモリ -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">CPU & メモリ使用率</div>
                    <div class="card-body">
                        <div>
                            <div class="d-flex justify-content-between">
                                <span>CPU使用率:</span>
                                <span id="cpu-percent">0%</span>
                            </div>
                            <div class="progress">
                                <div id="cpu-progress" class="progress-bar" role="progressbar" style="width: 0%"></div>
                            </div>
                        </div>
                        <div class="mt-3">
                            <div class="d-flex justify-content-between">
                                <span>メモリ使用率:</span>
                                <span id="memory-percent">0%</span>
                            </div>
                            <div class="progress">
                                <div id="memory-progress" class="progress-bar" role="progressbar" style="width: 0%"></div>
                            </div>
                            <div class="mt-2 small" id="memory-details"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- ディスク情報 -->
        <div class="card">
            <div class="card-header">ディスク使用率</div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-sm table-hover">
                        <thead>
                            <tr>
                                <th>デバイス</th>
                                <th>マウントポイント</th>
                                <th>ファイルシステム</th>
                                <th>合計</th>
                                <th>使用中</th>
                                <th>空き</th>
                                <th>使用率</th>
                            </tr>
                        </thead>
                        <tbody id="disk-info">
                            <tr><td colspan="7">読込中...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <!-- プロセス情報 -->
        <div class="card">
            <div class="card-header">トッププロセス (CPU使用率)</div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-sm table-hover">
                        <thead>
                            <tr>
                                <th>PID</th>
                                <th>名前</th>
                                <th>ユーザー</th>
                                <th>CPU %</th>
                                <th>メモリ %</th>
                            </tr>
                        </thead>
                        <tbody id="process-info">
                            <tr><td colspan="5">読込中...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- スキャン中モーダル -->
    <div class="modal fade" id="scanningModal" tabindex="-1" aria-labelledby="scanningModalLabel" aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="scanningModalLabel">ネットワークスキャン中</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="閉じる"></button>
                </div>
                <div class="modal-body">
                    <p>ネットワーク上のLinuxサーバーをスキャンしています...</p>
                    <div class="progress">
                        <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 100%"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // グローバル変数
        let refreshInterval = 5000;
        let refreshTimer;
        let scanningModalInstance = null;
        
        // DOMが読み込まれたら実行
        document.addEventListener('DOMContentLoaded', function() {
            // 初期化処理
            initTheme();
            loadServerList();
            
            // テーマ切り替えボタンのイベント
            document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
            
            // サーバースキャンイベント
            document.addEventListener('click', function(e) {
                if (e.target.closest('[data-action="scan"]')) {
                    e.preventDefault();
                    scanServers();
                }
            });
            
            // サーバー選択イベント
            document.getElementById('server-list').addEventListener('click', function(e) {
                const link = e.target.closest('[data-ip]');
                if (link && link.getAttribute('data-ip') !== 'loading') {
                    e.preventDefault();
                    setServer(link.getAttribute('data-ip'));
                }
            });
            
            // 初回データ取得
            fetchAndUpdateData();
        });
        
        // テーマの初期化
        function initTheme() {
            // サーバーから現在のテーマ設定を取得（ここでは簡易的にlightをデフォルトとする）
            const currentTheme = '{{ config.theme }}' || 'light';
            if (currentTheme === 'dark') {
                document.body.classList.add('dark-theme');
                document.getElementById('theme-icon').textContent = '🌙';
            } else {
                document.body.classList.remove('dark-theme');
                document.getElementById('theme-icon').textContent = '☀️';
            }
        }
        
        // テーマ切り替え
        function toggleTheme() {
            const isDark = document.body.classList.contains('dark-theme');
            const newTheme = isDark ? 'light' : 'dark';
            
            // テーマ切り替え
            if (newTheme === 'dark') {
                document.body.classList.add('dark-theme');
                document.getElementById('theme-icon').textContent = '🌙';
            } else {
                document.body.classList.remove('dark-theme');
                document.getElementById('theme-icon').textContent = '☀️';
            }
            
            // サーバーに設定を保存
            fetch('/api/set_theme', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ theme: newTheme })
            });
        }
        
        // サーバーリストを読み込む
        function loadServerList() {
            fetch('/api/servers')
                .then(response => response.json())
                .then(data => updateServerList(data));
        }
        
        // サーバーリストを更新
        function updateServerList(servers) {
            const serverList = document.getElementById('server-list');
            
            // 区切り線と「読み込み中...」の項目以外を削除
            const items = serverList.querySelectorAll('.dropdown-item:not([data-action="scan"])');
            items.forEach(item => {
                if (!item.closest('li').querySelector('hr')) {
                    item.closest('li').remove();
                }
            });
            
            // 「読み込み中...」の項目を非表示
            const loadingItem = serverList.querySelector('[data-ip="loading"]');
            if (loadingItem) {
                loadingItem.closest('li').style.display = 'none';
            }
            
            // サーバーがない場合
            if (servers.length === 0) {
                const li = document.createElement('li');
                const a = document.createElement('a');
                a.className = 'dropdown-item disabled';
                a.setAttribute('href', '#');
                a.textContent = 'サーバーが見つかりません';
                li.appendChild(a);
                serverList.appendChild(li);
                return;
            }
            
            // サーバーリストを追加
            servers.forEach(server => {
                const li = document.createElement('li');
                const a = document.createElement('a');
                a.className = 'dropdown-item';
                a.setAttribute('href', '#');
                a.setAttribute('data-ip', server.ip);
                
                let displayName = `${server.hostname} (${server.ip})`;
                if (server.is_local) {
                    displayName += ' [ローカル]';
                }
                
                a.textContent = displayName;
                li.appendChild(a);
                serverList.appendChild(li);
            });
        }
        
        // サーバースキャンを開始
        function scanServers() {
            // スキャン中モーダルを表示
            const scanningModal = new bootstrap.Modal(document.getElementById('scanningModal'));
            scanningModal.show();
            scanningModalInstance = scanningModal;
            
            // サーバースキャンAPIを呼び出し
            fetch('/api/scan_servers', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(() => {
                // 3秒後にサーバーリストを取得
                setTimeout(() => {
                    fetch('/api/servers')
                        .then(response => response.json())
                        .then(data => {
                            updateServerList(data);
                            
                            // モーダルを閉じる
                            if (scanningModalInstance) {
                                scanningModalInstance.hide();
                                scanningModalInstance = null;
                            }
                        });
                }, 3000);
            });
        }
        
        // サーバーを設定
        function setServer(ip) {
            fetch('/api/set_server', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ ip: ip })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    // データを再取得
                    fetchAndUpdateData();
                }
            });
        }
        
        // データ取得と表示を行う関数
        function fetchAndUpdateData() {
            // 既存のタイマーをクリア
            if (refreshTimer) {
                clearTimeout(refreshTimer);
            }
            
            // システム情報を取得
            fetch('/api/system_info')
                .then(response => response.json())
                .then(data => {
                    let html = '';
                    for (const [key, value] of Object.entries(data)) {
                        html += `<tr><td>${key}:</td><td>${value}</td></tr>`;
                    }
                    document.getElementById('system-info').innerHTML = html;
                });
            
            // リソース情報を取得
            fetch('/api/resources')
                .then(response => response.json())
                .then(data => {
                    // 更新時間
                    document.getElementById('refresh-time').textContent = data.time;
                    
                    // CPU情報
                    const cpuPercent = data.cpu.percent;
                    document.getElementById('cpu-percent').textContent = `${cpuPercent}%`;
                    const cpuProgress = document.getElementById('cpu-progress');
                    cpuProgress.style.width = `${cpuPercent}%`;
                    
                    if (cpuPercent > 90) {
                        cpuProgress.className = 'progress-bar bg-danger';
                    } else if (cpuPercent > 70) {
                        cpuProgress.className = 'progress-bar bg-warning';
                    } else {
                        cpuProgress.className = 'progress-bar bg-success';
                    }
                    
                    // メモリ情報
                    const memPercent = data.memory.percent;
                    document.getElementById('memory-percent').textContent = `${memPercent}%`;
                    const memProgress = document.getElementById('memory-progress');
                    memProgress.style.width = `${memPercent}%`;
                    
                    if (memPercent > 90) {
                        memProgress.className = 'progress-bar bg-danger';
                    } else if (memPercent > 70) {
                        memProgress.className = 'progress-bar bg-warning';
                    } else {
                        memProgress.className = 'progress-bar bg-success';
                    }
                    
                    document.getElementById('memory-details').textContent = 
                        `合計: ${data.memory.total} | 使用中: ${data.memory.used} | 利用可能: ${data.memory.available}`;
                    
                    // ディスク情報
                    let diskHtml = '';
                    data.disk.forEach(disk => {
                        let rowClass = '';
                        if (disk.percent > 90) {
                            rowClass = 'table-danger';
                        } else if (disk.percent > 70) {
                            rowClass = 'table-warning';
                        }
                        
                        diskHtml += `
                            <tr class="${rowClass}">
                                <td>${disk.device}</td>
                                <td>${disk.mountpoint}</td>
                                <td>${disk.fstype}</td>
                                <td>${disk.total}</td>
                                <td>${disk.used}</td>
                                <td>${disk.free}</td>
                                <td>
                                    <div class="d-flex align-items-center">
                                        <div class="progress flex-grow-1" style="height: 5px;">
                                            <div class="progress-bar ${disk.percent > 90 ? 'bg-danger' : disk.percent > 70 ? 'bg-warning' : 'bg-success'}" 
                                                role="progressbar" style="width: ${disk.percent}%"></div>
                                        </div>
                                        <span class="ms-2">${disk.percent}%</span>
                                    </div>
                                </td>
                            </tr>
                        `;
                    });
                    document.getElementById('disk-info').innerHTML = diskHtml;
                });
            
            // プロセス情報を取得
            fetch('/api/processes')
                .then(response => response.json())
                .then(data => {
                    let processHtml = '';
                    data.forEach(process => {
                        processHtml += `
                            <tr>
                                <td>${process.pid}</td>
                                <td>${process.name}</td>
                                <td>${process.username}</td>
                                <td>${process.cpu_percent.toFixed(1)}%</td>
                                <td>${process.memory_percent}%</td>
                            </tr>
                        `;
                    });
                    document.getElementById('process-info').innerHTML = processHtml;
                });
            
            // 次回のデータ更新をスケジュール
            refreshTimer = setTimeout(fetchAndUpdateData, refreshInterval);
        }
    </script>
</body>
</html>
    '''
    
    # テンプレートファイルを保存
    with open('templates/index.html', 'w') as f:
        f.write(html_template)
    
    # 最初のネットワークスキャンを開始
    print('初期ネットワークスキャンを開始中...')
    scan_thread = threading.Thread(target=scan_network)
    scan_thread.daemon = True
    scan_thread.start()
    
    print('サーバー監視アプリを起動します...')
    print('ブラウザで http://localhost:5000 にアクセスしてください')
    app.run(host='0.0.0.0', port=5000, debug=True)
