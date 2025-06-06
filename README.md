# ServerMonitor

リアルタイムサーバー監視ダッシュボード

## 機能

- CPU使用率の監視とリアルタイムグラフ表示
- メモリ使用率とスワップ使用率の監視
- ディスク使用率の監視
- システム温度情報の表示（sensorsコマンド対応）
- GPU情報の表示
- ネットワークインターフェース情報
- ダークテーマ対応
- 横長モニター最適化デザイン

## 必要な環境

- Python 3.6以上
- Ubuntu/Linux系OS
- lm-sensors（温度情報取得用）

## セットアップ

### 1. 依存関係のインストール

```bash
# Python依存関係
pip3 install psutil flask

# システム依存関係（Ubuntu/Debian）
sudo apt-get update
sudo apt-get install lm-sensors

# システム依存関係（CentOS/RHEL/Fedora）
sudo yum install lm_sensors
# または
sudo dnf install lm_sensors
```

### 2. sensorsの設定

```bash
sudo sensors-detect
```

### 3. アプリケーションの起動

```bash
python3 app.py
```

### 4. ブラウザでアクセス

http://localhost:5000 または http://サーバーIP:5000

## 機能説明

### リアルタイム監視
- 5秒間隔でのデータ自動更新
- CPU使用率の時系列グラフ表示
- 使用率に応じた色分け表示

### 温度監視
- CPU温度の表示
- NVMe SSD温度の表示
- 温度に応じた警告色表示

### ダークテーマ
- GitHub風のダークカラーパレット
- 長時間の監視作業に配慮した目に優しいデザイン

### 横長モニター対応
- CSS Gridによる柔軟なレイアウト
- 超横長モニター（2560px以上）での最適表示
- 温度情報の横並び表示

## スクリーンショット

![ダッシュボード](screenshot.png)

## API エンドポイント

### システム情報
- `GET /api/system` - システム基本情報
- `GET /api/cpu` - CPU情報
- `GET /api/memory` - メモリ情報
- `GET /api/disk` - ディスク情報
- `GET /api/temperature` - 温度情報
- `GET /api/gpu` - GPU情報
- `GET /api/network` - ネットワーク情報
- `GET /api/all` - 全情報

### レスポンス例

```json
{
  "timestamp": "2025-06-06 12:34:56",
  "system": {
    "hostname": "test-server",
    "os": "Linux",
    "uptime": "5日 12時間 34分"
  },
  "cpu": {
    "usage_percent": 25.4,
    "cores": 8,
    "threads": 16
  },
  "memory": {
    "total": 32.0,
    "used": 8.5,
    "percent": 26.6
  }
}
```

## トラブルシューティング

### 温度情報が表示されない場合

```bash
# sensorsコマンドが動作するか確認
sensors

# JSON形式で出力できるか確認
sensors -j
```

### ポート5000が使用できない場合

app.pyの最後の行を編集：

```python
app.run(host='0.0.0.0', port=8080, debug=True)
```

### 権限エラーが発生する場合

```bash
# アプリケーションを通常ユーザーで実行
python3 app.py

# 必要に応じてsudoで実行
sudo python3 app.py
```

## カスタマイズ

### 更新間隔の変更

templates/index.htmlの以下の行を編集：

```javascript
// 定期的な更新（5秒ごと）
setInterval(fetchAllData, 5000);
```

### ダークテーマの無効化

templates/index.htmlの以下の行を削除：

```html
<html lang="ja" data-bs-theme="dark">
```

## 開発

### 開発環境のセットアップ

```bash
# 仮想環境の作成
python3 -m venv dev_env
source dev_env/bin/activate

# 依存関係のインストール
pip install -r requirements.txt

# 開発サーバーの起動
python3 app.py
```

### プロジェクト構造

```
ServerMonitor/
├── app.py              # メインアプリケーション
├── templates/
│   └── index.html      # ダッシュボードHTML
├── requirements.txt    # Python依存関係
├── .gitignore         # Git無視ファイル設定
└── README.md          # プロジェクト説明
```

## 貢献

1. このリポジトリをフォーク
2. 機能ブランチを作成 (`git checkout -b feature/new-feature`)
3. 変更をコミット (`git commit -am 'Add new feature'`)
4. ブランチにプッシュ (`git push origin feature/new-feature`)
5. プルリクエストを作成

## ライセンス

MIT License

## 作者

te-adachi-dev

## 更新履歴

### v1.0.0 (2025-06-06)
- 初回リリース
- 基本的な監視機能実装
- ダークテーマ対応
- 横長モニター最適化
