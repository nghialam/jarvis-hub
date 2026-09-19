# Hướng Dẫn Sử Dụng Jarvis Hub 3.0

> Tài liệu hướng dẫn toàn diện cho Jarvis Hub — hệ thống quản lý đầu tư chứng khoán tự động với tích hợp AI, Telegram bot, và web dashboard.

---

## Mục Lục

1. [Tổng Quan](#1-tổng-quan)
2. [Cài Đặt & Cấu Hình](#2-cài-đặt--cấu-hình)
3. [Khởi Động Ứng Dụng](#3-khởi-động-ứng-dụng)
4. [Chức Năng Chính](#4-chức-năng-chính)
5. [Telegram Bot](#5-telegram-bot)
6. [Cron Jobs (Nhiệm Vụ Tự Động)](#6-cron-jobs-nhiệm-vụ-tự-động)
7. [API Reference](#7-api-reference)
8. [Cơ Sở Dữ Liệu](#8-cơ-sở-dữ-liệu)
9. [Quản Lý Broker Accounts](#9-quản-lý-broker-accounts)
10. [Scripts & Tools](#10-scripts--tools)
11. [Deployment](#11-deployment)
12. [Troubleshooting](#12-troubleshooting)
13. [Phân Quyền & Bảo Mật](#13-phân-quyền--bảo-mật)

---

## 1. Tổng Quan

Jarvis Hub 3.0 là hệ thống quản lý đầu tư chứng khoán toàn diện, tích hợp:

- **API Broker** — kết nối FAISTRY, VPS, HBSecure, SSI để lấy dữ liệu tài khoản, lệnh, portfolio
- **Phân tích kỹ thuật tự động** — PPN (Phá Đảo), Breakout, tin tức, smart news
- **Telegram Bot** — auto-brief hàng ngày, thông báo cảnh báo, quét tin tức
- **Web Dashboard** — giao diện quản lý portfolio, theo dõi giá, báo cáo hiệu suất
- **Cron Jobs** — tự động thu thập dữ liệu, phân tích, gửi thông báo
- **Lịch Sử Lệnh & Báo Cáo** — tracking giao dịch, stop-loss, PnL

### Kiến Trúc

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Telegram Bot │    │ Web Dashboard│    │  Cron Jobs  │
│  (Auto-brief)│    │ (Flask App)  │    │ (Scheduled) │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
              ┌────────────▼────────────┐
              │   Flask API Server      │
              │   (Port 8100)           │
              └────────────┬────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐
│  API Brokers  │  │  Analysis   │  │  Database    │
│  (FAPI/VPS)   │  │  Engines    │  │  (SQLite)    │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## 2. Cài Đặt & Cấu Hình

### Yêu Cầu Hệ Thống

- Python 3.10+
- SQLite (tích hợp Python)
- Telegram Bot Token
- Broker API Credentials

### Cài Đặt

```bash
# Clone repository
git clone https://github.com/nghialam/jarvis-hub.git
cd jarvis-hub

# Cài đặt dependencies
pip install -r requirements.txt

# Cài đặt pre-commit hooks
pre-commit install
```

### Cấu Hình (config.yaml)

Tạo file `config.yaml` tại thư mục gốc:

```yaml
# ===== Cấu hình chung =====
app:
  name: "Jarvis Hub"
  version: "3.0"
  port: 8100
  debug: false

# ===== Database =====
database:
  path: "data/jarvis.db"
  backup_before_create: true

# ===== Telegram Bot =====
telegram:
  bot_token: "[REDACTED]"  # Tự điền token từ BotFather
  chat_id: "[REDACTED]"     # Chat ID để gửi thông báo
  group_chat_id: "[REDACTED]"  # Group chat (optional)

# ===== Broker APIs =====
brokers:
  fapi:
    base_url: "https://api.faactivity.com"
    api_key: "[REDACTED]"
    secret: "[REDACTED]"
  vps:
    base_url: "https://api.vps.com.vn"
    api_key: "[REDACTED]"
    secret: "[REDACTED]"
  hbsecure:
    base_url: "https://api.hbsecure.com.vn"
    api_key: "[REDACTED]"
    secret: "[REDACTED]"
  ssi:
    base_url: "https://api.ssi.com.vn"
    api_key: "[REDACTED]"
    secret: "[REDACTED]"

# ===== AI / LLM =====
ai:
  openai_api_key: "[REDACTED]"  # Nền tảng AI phân tích
  model: "gpt-4"               # Model mặc định

# ===== Cron Jobs =====
cron:
  daily_brief_time: "09:30"     # Giờ gửi auto-brief hàng ngày
  news_scan_interval: "300"     # Quét tin tức mỗi 5 phút (giây)
  market_data_refresh: "60"     # Làm mới dữ liệu thị trường mỗi 1 phút

# ===== Analysis Engine =====
analysis:
  ppn_threshold: 0.02           # Ngưỡng PPN (2%)
  breakout_lookback: 20         # Lookback period cho breakout
  news_lookback_hours: 24       # Quét tin 24h qua

# ===== Dashboard =====
dashboard:
  template_folder: "dashboard/templates"
  static_folder: "dashboard/static"
```

> **Lưu ý bảo mật:** Không commit `config.yaml` lên Git! Thêm vào `.gitignore`. Sử dụng biến môi trường hoặc `.env` cho sensitive data.

---

## 3. Khởi Động Ứng Dụng

### Development Mode

```bash
# Khởi động Flask app
python app.py
```

App sẽ chạy trên `http://localhost:8100`

### Production Mode (Gunicorn)

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8100 app:app
```

### Kiểm Tra Trạng Thái

```bash
# Kiểm tra API health
curl http://localhost:8100/api/health

# Kiểm tra database
curl http://localhost:8100/api/status
```

---

## 4. Chức Năng Chính

### 4.1 Tổng Quan Dashboard (S01)

Trang tổng quan hiển thị:

- **Tổng hợp tài khoản** — số dư, PnL, margin usage từ các broker accounts
- **Cảnh báo hệ thống** — kết nối broker, API errors, cron job failures
- **Thống kê nhanh** — số lượng lệnh hôm nay, số lượng cảnh báo đang active
- **Biểu đồ hiệu suất** — PnL theo thời gian, allocation theo sector

**Cách truy cập:** Mở `http://localhost:8100/dashboard`

### 4.2 Phân Tích PPN (M01)

**PPN (Phá Đảo)** — phát hiện giá phá vỡ resistance/support quan trọng.

#### Cách hoạt động:

1. Tự động quét các cặp giá/stock có potential breakout
2. Phân tích volume surge sau breakout
3. Tính toán target price dựa trên chiều cao pattern
4. Gửi cảnh báo qua Telegram khi phát hiện signal

#### Parameter:

```yaml
analysis:
  ppn_threshold: 0.02    # Ngưỡng % (mặc định 2%)
```

#### Output Telegram:

```
🔔 PPN SIGNAL
Stock: VIC
Type: Breakout Resistance
Price: 228.000
Volume: 1.5M (+250% avg)
Target: 245.000
Stop Loss: 218.000
```

### 4.3 Phân Tích Breakout (M03)

Tương tự PPN nhưng tập trung vào breakout patterns:

- **Ascending Triangle**
- **Flag/Pennant**
- **Cup & Handle**
- **Double Bottom/Top**

#### Config Breakout:

```yaml
analysis:
  breakout_lookback: 20     # Số ngày xem xét pattern
  min_volume_ratio: 1.5     # Tỷ lệ volume so với average
```

### 4.4 Tin Tức & Sentiment (N02, Smart News)

#### News Aggregation:

- Quét tin từ CafeF, Vietstock, VnExpress
- Phân tích sentiment (bullish/bearish/neutral)
- Gắn nhãn ngành/ticker
- Tự động gửi tin nóng qua Telegram

#### Smart News:

- Phân tích ảnh hưởng của tin tức đến giá stock
- Phân loại:earnings, M&A, macro policy, insider trading
- Tính confidence score dựa trên history của ticker

### 4.5 Theo Dõi Giá (S02)

- Lấy giá real-time từ proxy APIs (FAPI, VPS)
- Cập nhật last price, high/low, volume
- Alert khi giá vượt ngưỡng设定的

### 4.6 Lịch Sử Lệnh (S03)

- Lưu toàn bộ lệnh: buy, sell, pending, cancelled
- Phân loại theo ngày/tuần/tháng
- Filter theo symbol, status, broker
- Export báo cáo CSV

### 4.7 Portfolio (M04)

- Theo dõi danh mục từ nhiều broker accounts
- Tính tổng PnL, allocation theo sector
- Rebalancing suggestions

### 4.8 Watchlist

- Danh sách theo dõi tùy chỉnh
- Real-time price alerts
- Auto-scan PPN/breakout cho watchlist items

### 4.9 Cảnh Báo (N01)

- Hệ thống alerts cho:
  - Price target reached
  - Volume spike
  - PPN/Breakout signals
  - News impact alerts
  - Portfolio margin alert

---

## 5. Telegram Bot

### Bật Telegram Bot

```yaml
telegram:
  bot_token: "YOUR_BOT_TOKEN"
  chat_id: "YOUR_CHAT_ID"
```

### Các Tin Nhắn Tự Động

1. **Auto-Brief Hàng Ngày** — tóm tắt thị trường, tin tức, signals
2. **PPN Signals** — thông báo breakout ngay khi phát hiện
3. **News Alerts** — tin nóng theo ticker yêu thích
4. **Portfolio Updates** — thay đổi PnL, allocation

### Custom Commands

```
/start       — Bắt đầu sử dụng
/status      — Kiểm tra trạng thái hệ thống
/portfolio   — Xem portfolio hiện tại
/price Ticker — Lấy giá real-time
/alert set TICKER 100 — Đặt alert giá
/alert list   — Xem danh sách alerts
```

---

## 6. Cron Jobs (Nhiệm Vụ Tự Động)

### Cấu Hình Cron

```yaml
cron:
  daily_brief_time: "09:30"
  news_scan_interval: "300"
  market_data_refresh: "60"
  ppn_scan_interval: "300"
  breakout_scan_interval: "300"
  portfolio_update: "3600"  # Mỗi giờ
```

### Danh Sách Cron Jobs

| Job | Interval | Mô Tả |
|---|---|---|
| `market_data_refresh` | Every 60s | Cập nhật giá từ FAPI/VPS proxies |
| `news_scan` | Every 5 min | Quét tin mới từ sources |
| `ppn_scan` | Every 5 min | Chạy PPN analysis |
| `breakout_scan` | Every 5 min | Chạy breakout analysis |
| `daily_brief` | 09:30 | Auto-brief hàng ngày |
| `portfolio_update` | Every 1h | Làm mới portfolio data |
| `alert_check` | Every 5 min | Kiểm tra price alerts |

### Quản Lý Cron Jobs

```python
from core.scheduler import Scheduler

# Khởi tạo
scheduler = Scheduler(config)

# Kích hoạt tất cả jobs
scheduler.start()

# Dừng một job cụ thể
scheduler.stop('ppn_scan')

# Xem trạng thái
scheduler.status()
```

---

## 7. API Reference

### 7.1 Health & Status

| Method | Endpoint | Mô Tả |
|---|---|---|
| GET | `/api/health` | Kiểm tra API health |
| GET | `/api/status` | Trạng thái hệ thống |
| GET | `/api/config` | Xem cấu hình hiện tại |

### 7.2 Market Data

| Method | Endpoint | Mô Tả |
|---|---|---|
| GET | `/api/price/TICKER` | Giá real-time |
| GET | `/api/price/TICKER/history` | Lịch sử giá |
| GET | `/api/sector/overview` | Tổng quan sector |
| GET | `/api/market/overview` | Tổng quan thị trường |

### 7.3 Analysis

| Method | Endpoint | Mô Tả |
|---|---|---|
| GET | `/api/analysis/ppn` | Danh sách PPN signals |
| GET | `/api/analysis/breakout` | Breakout patterns |
| GET | `/api/analysis/news` | Tin tức & sentiment |
| GET | `/api/analysis/ai/brief` | AI brief (OpenAI) |

### 7.4 Broker & Portfolio

| Method | Endpoint | Mô Tả |
|---|---|---|
| GET | `/api/portfolio` | Portfolio overview |
| GET | `/api/orders` | Lịch sử lệnh |
| GET | `/api/accounts` | Danh sách broker accounts |
| POST | `/api/accounts` | Thêm broker account mới |
| DELETE | `/api/accounts/:id` | Xóa broker account |

### 7.5 Watchlist & Alerts

| Method | Endpoint | Mô Tả |
|---|---|---|
| GET | `/api/watchlist` | Danh sách watchlist |
| POST | `/api/watchlist` | Thêm vào watchlist |
| DELETE | `/api/watchlist/:id` | Xóa khỏi watchlist |
| GET | `/api/alerts` | Danh sách alerts |
| POST | `/api/alerts` | Tạo alert mới |
| DELETE | `/api/alerts/:id` | Xóa alert |

### 7.6 News

| Method | Endpoint | Mô Tả |
|---|---|---|
| GET | `/api/news` | Danh sách tin tức |
| POST | `/api/news/sources` | Thêm news source |
| GET | `/api/news/source/status` | Trạng thái scraping |

### 7.7 Cron Management

| Method | Endpoint | Mô Tả |
|---|---|---|
| GET | `/api/cron/jobs` | Danh sách cron jobs |
| POST | `/api/cron/jobs/:id/run` | Chạy job ngay |
| POST | `/api/cron/jobs/:id/enable` | Bật job |
| POST | `/api/cron/jobs/:id/disable` | Tắt job |

### 7.8 Reports

| Method | Endpoint | Mô Tả |
|---|---|---|
| GET | `/api/reports/performance` | Báo cáo hiệu suất |
| GET | `/api/reports/net-worth` | Lịch sử net worth |
| GET | `/api/reports/export/csv` | Export CSV |

---

## 8. Cơ Sở Dữ Liệu

### Cấu Hình

```yaml
database:
  path: "data/jarvis.db"
  backup_before_create: true
```

### Schema Chính

#### Broker Accounts (`broker_accounts`)

| Column | Type | Mô Tả |
|---|---|---|
| id | INTEGER | Primary key |
| name | TEXT | Tên broker (FAPI, VPS...) |
| api_key | TEXT | API key (encrypted) |
| api_secret | TEXT | API secret (encrypted) |
| base_url | TEXT | URL của broker API |
| status | TEXT | active/inactive |
| created_at | DATETIME | Thời gian tạo |

#### Market Data (`market_data`)

| Column | Type | Mô Tả |
|---|---|---|
| id | INTEGER | Primary key |
| symbol | TEXT | Mã chứng khoán |
| price | REAL | Giá |
| volume | INTEGER | Volume |
| high | REAL | Cao nhất |
| low | REAL | Thấp nhất |
| timestamp | DATETIME | Thời gian cập nhật |

#### Orders (`orders`)

| Column | Type | Mô Tả |
|---|---|---|
| id | INTEGER | Primary key |
| account_id | INTEGER | FK -> broker_accounts |
| symbol | TEXT | Mã chứng khoán |
| action | TEXT | buy/sell |
| price | REAL | Giá |
| quantity | INTEGER | Số lượng |
| status | TEXT | pending/completed/cancelled |
| created_at | DATETIME | Thời gian tạo |

#### Alerts (`alerts`)

| Column | Type | Mô Tả |
|---|---|---|
| id | INTEGER | Primary key |
| ticker | TEXT | Mã chứng khoán |
| type | TEXT | price/ppn/breakout/news |
| value | REAL | Giá trị ngưỡng |
| status | TEXT | active/fired/resolved |
| created_at | DATETIME | Thời gian tạo |

#### News (`news`)

| Column | Type | Mô Tả |
|---|---|---|
| id | INTEGER | Primary key |
| title | TEXT | Tiêu đề |
| content | TEXT | Nội dung |
| ticker | TEXT | Mã liên quan |
| source | TEXT | Nguồn tin |
| sentiment | TEXT | positive/neutral/negative |
| timestamp | DATETIME | Thời gian |

### Backup Database

```python
from core.db import Database

db = Database()
db.backup()  # Tự động backup trước khi recreate
```

Backup được lưu tại `data/backups/`

---

## 9. Quản Lý Broker Accounts

### Thêm Broker Account Mới

```python
from core.broker_manager import BrokerManager

manager = BrokerManager()
manager.add_account({
    'name': 'FAPI',
    'api_key': '[REDACTED]',
    'api_secret': '[REDACTED]',
    'base_url': 'https://api.faactivity.com',
    'status': 'active'
})
```

### API Endpoint

```bash
# Thêm broker account
curl -X POST http://localhost:8100/api/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "FAPI",
    "api_key": "[REDACTED]",
    "api_secret": "[REDACTED]",
    "base_url": "https://api.faactivity.com",
    "status": "active"
  }'
```

### API Endpoints Chi Tiết

```bash
# Lấy danh sách accounts
GET /api/accounts

# Lấy chi tiết một account
GET /api/accounts/:id

# Cập nhật account
PUT /api/accounts/:id

# Xóa account
DELETE /api/accounts/:id

# Test kết nối broker
POST /api/accounts/:id/test
```

### Hỗ Trợ Brokers

| Broker | API | Status |
|---|---|---|
| FAPI (FaActivity) | HTTP REST | ✅ |
| VPS | HTTP REST | ✅ |
| HBSecure | HTTP REST | ✅ |
| SSI | HTTP REST | ✅ |

---

## 10. Scripts & Tools

### 10.1 QuickDep Script

```bash
# Tạo mẫu lệnh DCA
python scripts/quickdep.py --ticker VIC --amount 10000000 --frequency weekly
```

### 10.2 DCA Analysis

```bash
# Phân tích chiến lược DCA
python scripts/dca_analysis.py --ticker VIC --start 2023-01-01 --amount 1000000
```

### 10.3 Graph Visualization

```bash
# Tạo biểu đồ kỹ thuật
python scripts/graphs.py --ticker VIC --type candle --range 30d
```

### 10.4 Benchmark Backtesting

```bash
# Backtest chiến lược trên benchmark
python scripts/benchmark_backtesting.py --benchmark VNI --start 2023-01-01
```

### 10.5 Cron Execution Scripts

```bash
# Chạy script thu thập dữ liệu thị trường
python scripts/market_data.py

# Chạy phân tích PPN
python scripts/ppn_scan.py

# Chạy phân tích breakout
python scripts/breakout_scan.py

# Chạy quét tin tức
python scripts/news_scan.py
```

### 10.6 Integration Tests

```bash
# Chạy tất cả tests
python -m pytest tests/

# Chạy test cho module cụ thể
python -m pytest tests/test_broker_api.py
```

---

## 11. Deployment

### 11.1 Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8100

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8100", "app:app"]
```

```bash
# Build và chạy
docker build -t jarvis-hub .
docker run -p 8100:8100 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config.yaml:/app/config.yaml \
  --name jarvis-hub \
  jarvis-hub
```

### 11.2 Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 11.3 SSL với Let's Encrypt

```bash
sudo certbot --nginx -d your-domain.com
```

### 11.4 Systemd Service

```ini
[Unit]
Description=Jarvis Hub
After=network.target

[Service]
Type=simple
User=nghialam
WorkingDirectory=/Users/nghialam/jarvis-hub
ExecStart=/usr/local/bin/gunicorn -w 4 -b 0.0.0.0:8100 app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo cp deploy/jarvis-hub.service /etc/systemd/system/
sudo systemctl enable jarvis-hub
sudo systemctl start jarvis-hub
```

### 11.5 Environment Variables

```bash
export JARVIS_DB_PATH="data/jarvis.db"
export TELEGRAM_BOT_TOKEN="YOUR_TOKEN"
export TELEGRAM_CHAT_ID="YOUR_CHAT_ID"
export OPENAI_API_KEY="YOUR_KEY"
```

---

## 12. Troubleshooting

### Lỗi Thường Gặp

#### 1. Không kết nối được Telegram Bot

**Triệu chứng:** Auto-brief không gửi được

**Kiểm tra:**
- Token có chính xác không?
- Chat ID có đúng không?
- Bot đã được add vào group chưa? (nếu dùng group chat)

**Fix:**
```bash
# Test kết nối
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

#### 2. API Broker trả về 403

**Triệu chứng:** Không lấy được data từ FAPI/VPS

**Kiểm tra:**
- API key/secret có đúng không?
- API key có hết hạn không?
- Permission có đủ không?

**Fix:** Tạo lại API key từ panel của broker

#### 3. Database locked

**Triệu chứng:** `sqlite3.OperationalError: database is locked`

**Fix:**
```bash
# Kiểm tra process nào đang truy cập DB
lsof data/jarvis.db

# Restart app
sudo systemctl restart jarvis-hub
```

#### 4. Cron jobs không chạy

**Triệu chứng:** Market data không update

**Kiểm tra:**
```bash
# Xem trạng thái cron jobs
curl http://localhost:8100/api/cron/jobs

# Xem logs
tail -100 /var/log/jarvis-hub/error.log
```

#### 5. Memory usage cao

**Triệu chứng:** App chậm, crash

**Fix:**
- Giảm số lượng Gunicorn workers
- Tăng swap space
- Close unused tabs/applications

### Logs

```bash
# Xem real-time logs
tail -f /var/log/jarvis-hub/app.log

# Xem error logs
tail -f /var/log/jarvis-hub/error.log

# Kiểm tra health
curl http://localhost:8100/api/health
```

---

## 13. Phân Quyền & Bảo Mật

### Hệ Thống Phân Quyền

| Role |权限 | Description |
|---|---|---|
| admin | full | Truy cập toàn bộ hệ thống |
| user | read-only | Chỉ xem dashboard và data |
| analyst | analysis | Truy cập analysis endpoints |

### JWT Authentication

```bash
# Login
curl -X POST http://localhost:8100/api/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "[REDACTED]"}'

# Sử dụng token
curl http://localhost:8100/api/portfolio \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Sensitive Data

| Type | Example | Cách Xử Lý |
|---|---|---|
| API Key | `fa-xxxx-xxxx` | Encrypt in DB |
| API Secret | `secret-xxxx` | Encrypt in DB |
| Telegram Token | `123456:ABC-DEF` | Environment variable |
| OpenAI Key | `sk-xxxx` | Environment variable |

### Các Bước Bảo Mật Khuyến Nghị

1. **Sử dụng `.env` file** cho sensitive data
2. **Không commit `config.yaml`** lên Git
3. **Sử dụng HTTPS** cho production
4. **Regular backup** database
5. **Review logs** thường xuyên
6. **Update dependencies** định kỳ
7. **Sử dụng firewall** chỉ allow port 8100 từ localhost

---

## Phụ Lục

### A. Tính Năng Theo Phase

| Phase | Features | Status |
|---|---|---|
| Phase 1 | Foundation, Broker APIs, Basic Dashboard | ✅ |
| Phase 2 | Analysis Engines, PPN, Breakout, News | ✅ |
| Phase 3 | Telegram Bot, Cron Jobs, Alerts | ✅ |
| Phase 4 | Portfolio, Reports, Watchlists | ✅ |
| Phase 5 | Deployment, CI/CD, Testing | ✅ |

### B. Quick Start

```bash
# 1. Cài đặt
git clone https://github.com/nghialam/jarvis-hub.git
cd jarvis-hub
pip install -r requirements.txt

# 2. Cấu hình
cp config.yaml.example config.yaml
# Edit config.yaml với credentials của bạn

# 3. Khởi động
python app.py

# 4. Mở dashboard
# http://localhost:8100
```

### C. Contributing

```bash
# Tạo branch mới
git checkout -b feature/your-feature

# Phát triển và test
python -m pytest tests/

# Commit và push
git add .
git commit -m "Add: your feature description"
git push origin feature/your-feature

# Tạo Pull Request
gh pr create --title "Your PR title" --body "Description"
```

### D. Contact & Support

- **Repository:** https://github.com/nghialam/jarvis-hub
- **Issues:** https://github.com/nghialam/jarvis-hub/issues
- **Documentation:** https://github.com/nghialam/jarvis-hub/docs

---

*Tài liệu được tạo tự động từ codebase live. Version 3.0 | September 2026*
