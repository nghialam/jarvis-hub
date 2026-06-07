# 📘 JARVIS HUB — HƯỚNG DẪN SỬ DỤNG CHO NGƯỜI DÙNG

**Phiên bản:** v2.0 — *Cập nhật: 2026-05-22*  
*Dành cho nhà đầu tư cá nhân, trader, và người quan tâm thị trường tài chính Việt Nam & toàn cầu.*

---

## 🎯 Jarvis Hub LÀ GÌ?

Jarvis Hub là công cụ **trợ lý AI tài chính** chạy hoàn toàn trên máy tính của bạn, giúp:

- ✅ **Tổng hợp tin tức** tự động từ các nguồn Cafef, VnExpress, Reuters...
- ✅ **Phân tích cổ phiếu/vàng/crypto** với chỉ số kỹ thuật và gợi ý MUA/HOLD/BÁN
- ✅ **Tra cứu thuật ngữ** tài chính kiểu dictionary
- ✅ **Theo dõi danh mục** (watchlist) giá realtime
- ✅ **Đánh giá thị trường hàng ngày** — tổng quan xu hướng

**Ưu điểm:** Dữ liệu luôn tươi (fetch từ Yahoo Finance), AI phân tích local (không cần internet ngoài RSS/API), bảo mật tuyệt đối (data không gửi đi đâu cả).

---

## 🚀 BẮT ĐẦU NHANH

### Bước 1: Mở Jarvis Hub

```bash
cd ~/jarvis-hub
python app.py
```

Mở trình duyệt và truy cập: **http://localhost:8100**

> 💡 Mẹo: Nếu thấy màn hình đen trống, chờ 30 giây để hệ thống fetch dữ liệu lần đầu.

### Bước 2: Làm quen giao diện

Dashboard có **6 tab chính** (menu bên trái):

| Tab | Biểu tượng | Dùng để làm gì? |
|-----|-----------|----------------|
| News Feed | 📰 Tin tức mới nhất + cảm xúc thị trường |
| Analysis | 📈 Phân tích chi tiết 1 mã cổ phiếu/vàng/crypto |
| Knowledge Base | 💡 Tra cứu thuật ngữ tài chính |
| Daily Snapshots | ⏰ Lịch sử briefing hàng ngày |
| Market Evaluation | 📊 Đánh giá tổng quan thị trường hôm nay |
| Watchlist | ⭐ Theo dõi danh sách yêu thích |

Bây giờ hãy khám phá từng tab! 👇

---

## 📰 TAB 1: TIN TỨC (NEWS FEED)

### Hiển thị gì?
- **5 bài news mới nhất** từ Cafef, VnExpress, Reuters...
- Mỗi bài có 4 thông tin: tiêu đề, tóm tắt, nguồn, cảm xúc (TÍCH CỰC / TIÊU CỰC / TRUNG LẬP)

### Cách dùng:
1. Nhìn tiêu đề → chọn đọc chi tiết trong phần "Chi tiết"
2. Màu sắc giúp bạn nắm nhanh: 🟢 Tích cực | 🔴 Tiêu cực | ⚪ Trung lập
3. Filter theo category (VN Stock, Global Economy, AI Tech...)

### Ví dụ thực tế:
```
[1] P/E của VNM là 24.5 — cao hơn trung bình ngành
   ☀️ TÍCH CỰC | Cafef Doanh nghiệp
   Tóm tắt: Sữa Vinamilch công bố lợi nhuận Q1 tăng...
```

---

## 📈 TAB 2: PHÂN TÍCH (ANALYSIS) — *Tính năng MẠNH NHẤT*

Đây là nơi bạn nhập mã cổ phiếu và nhận báo cáo phân tích chi tiết.

### Cách sử dụng:

**Bước 1:** Nhập symbol vào ô "Enter symbol"
- Cổ phiếu Việt Nam: `VNM`, `FRT`, `HPG`, `VC`... ( hệ thống tự thêm `.VN`)
- Vàng: `XAUUSD` hoặc `XAU/USD`
- Crypto: `BTC`, `ETH`, `SOL`

**Bước 2:** Nhấn Enter hoặc click nút 📊 "Analyze"

**Bước 3:** Chờ ~5-15 giây (hệ thống đang fetch dữ liệu real-time từ Yahoo Finance)

### Báo cáo trả về có những gì?

#### A) Dữ liệu thị trường
| Trường | Ý nghĩa |
|--------|---------|
| **Price** | Giá hiện tại (VNĐ cho cổ phiếu, USD cho vàng/crypto) |
| **Change %** | Hôm nay tăng/giảm bao nhiêu % |
| **Volume** | Khối lượng giao dịch hôm nay |
| **P/E** | Tỷ lệ giá/lợi nhuận — so sánh với ngành |
| **EPS** | Lợi nhuận trên mỗi cổ phiếu |
| **Market Cap** | Vốn hóa thị trường |

#### B) Chỉ số kỹ thuật (Technical Indicators)
|指標 | Ý nghĩa | Tín hiệu mua/bán |
|-----|---------|------------------|
| **SMA 20/50** | Đường trung bình động — giá nằm trên = xu hướng tăng |
| **RSI (14)** | Đo sức mạnh:<br>• >70 = Overbought (quá mua, dễ giảm)<br>• <30 = Oversold (quá bán, dễ tăng)<br>• 30-70 = Bình thường |
| **MACD** | Đắt/từ cross signal — histogram dương = bullish, âm = bearish |

#### C) Báo cáo AI (LLM Report) ⭐ *Độc quyền*
Hệ thống phân tích tự động bao gồm:

1. **📊 Xu hướng 3 khung thời gian**:
   - Ngắn hạn (1-5 ngày): Điểm vào/out tiềm năng
   - Trung hạn (1-4 tuần): Xu hướng chính sắp tới
   - Dài hạn (>1 tháng): So với SMA200, xu hướng vĩ mô

2. **📌 Support & Resistance**:
   - 3 mức Support: S1 (gần nhất), S2, S3 (mạnh)
   - 3 mức Resistance: R1 (gần nhất), R2, R3 (khó vượt)

3. **💡 Khuyến nghị**:
   - **MUA / HOLD / BÁN** — kèm lý do chi tiết
   - Confidence Score (% mức độ tin cậy)
   - Risk Level (Thấp/Trung bình/Cao)
   - Stop-loss đề xuất (giá cắt lỗ an toàn)

4. **🔥 Investment Catalysts**:
   - 2-3 catalyst BULLISH: báo cáo tài chính, cổ tức, mở rộng...
   - 2-3 catalyst BEARISH: rủi ro lạm phát, regulatory...

### Ví dụ thực tế:

**Nhập:** `VNM` → Enter  

**Kết quả bạn sẽ thấy:**
```
📊 VNM (Vietnam Dairy)
Giá: 57.500đ | +1.23% | Market Cap: 78.9T VND

--- Chỉ số kỹ thuật ---
SMA_20: 57.200 (GIÁ NẰM TRÊN) ✅ 
RSI(14): 62.3 (NEUTRAL)
MACD histogram: +20 (BULLISH 📈)

--- Báo cáo AI ---
# Khuyến nghị: HOLD

## Xu hướng:
- Ngắn hạn: Giá đang sideway, chờ breakout khỏi đỉnh SMA50...
- Trung hạn: Xu hướngsideway 3 tuần, vùng giao dịch 56k-58k
- Dài hạn: Trên SMA200 (trend tăng), nhưng P/E cao hơn ngảnh 

## Hỗ trợ & Kháng cự:
- S1: 57.000  S2: 56.500   S3: 55.800
- R1: 58.000  R2: 58.500   R3: 59.200

## Catalysts:
BULLISH: Báo cáo Q2 sắp công bố (dự kiến tốt), cổ tức mùa hè... 
BEARISH: Lạm phát tăng gây áp lực chi phí nguyên liệu...
```

💡 **Mẹo hay:** Sau khi phân tích lần 1, lần sau gọi lại cùng symbol sẽ **nhanh gấp 5-10 lần** (hệ thống đã cache kết quả LLM rồi).

---

## 💡 TAB 3: KNOWLEDGE BASE (NGÂN HÀNG THUẬT NGỮ)

Tra cứu các khái niệm tài chính như tra từ điển.

### Cách dùng:
1. Gõ thuật ngữ vào ô input: `P/E ratio`, `RSI`, `Moving Average`...
2. Nhấn 🔍 SEARCH hoặc Enter
3. Hệ thống tìm trong database nếu có, nếu không sẽ **tự động generate** định nghĩa bằng AI

### Ví dụ:

**Tìm:** `RSI`  
**Kết quả:**
```
## RSI (Relative Strength Index)
RSI là chỉ số kỹ thuật đo sức mạnh của mã cổ phiếu trên thang 0-100.

Các ngưỡng quan trọng:
• >70 → OVERBOUGHT (quá mua, có thể điều chỉnh giảm)
• <30 → OVERSOLD (quá bán, có thể bật tăng)
• 30-70 → bình thường

Ứng dụng: Kết hợp với MACD để xác nhận signals buy/sell.
Tags: stock, technical analysis, momentum indicator
```

### Mẹo:
- Nếu search ra "No results", click nút **"Generate with AI instead?"** — hệ thống tự viết definition rồi hỏi bạn có lưu lại không → click "Yes" để lần sau nhớ term này!
- Mỗi term có **tags** giúp filter/search later

---

## ⏰ TAB 4: DAILY SNAPSHOTS (LỊCH SỬ BRIEFING)

Xem các báo cáo daily briefing từng ngày đã được hệ thống tự động tạo.

### Cách dùng:
1. Click vào ngày muốn xem → mở Modal hiển thị briefing content đầy đủ
2. Mỗi snapshot là tóm tắt tin tức + sentiment của ngày đó
3. Xem lại để so sánh xu hướng thay đổi theo thời gian

### Ví dụ 1 ngày briefing có gì:
```
===== BRIEFING — 2026-05-20 =====
Tỷ giá (Vietcombank): USD/VND Transfer 24.250 | Sell 24.380

TIN TỨC & CẢM_XÚC [43 bài]
☀️ 20 tích cực | 🔴 15 tiêu cực | ⚪ 8 trung lập
Xu hướng: Tích cực

1. Vn Economy: Thị trường Chứng khoán giao dịch hết khối lượng...
   Source: Cafef Doanh nghiệp | ☀️ TÍCH CỰC
   Tóm tắt: Khối lượng giao dịch tăng 30% so với phiên trước, ...

2. Global Business: Fed giữ nguyên lãi suất 5.25-5.5%...
   Source: Reuters Business | ⚪ TRUNG LẬP
   
... (và 41 bài khác)
```

💡 **Mẹo:** Dùng tính năng này để theo dõi "bối cảnh" mỗi ngày — ví dụ hôm nay tin tích cực nhiều → xu hướng có thể bullish.

---

## 📊 TAB 5: MARKET EVALUATION (ĐÁNH GIÁ TỔNG QUAN)

Tự động generate báo cáo **đánh giá thị trường** dựa trên DỮ LIỆU MỚI NHẤT.

### Tính năng:
- Fetch dữ liệu real-time từ 7+ nguồn (VN-Index, USD/VND, BTC/ETH/SOL, Gold, DXY, Oil)
- AI LLM phân tích tổng quan và đưa ra **góc nhìn thị trường hôm nay**
- Báo cáo có cập nhật tự động mỗi lần mở tab

### Cách dùng:
1. Mở trang → dữ liệu được fetch ngay lập tức từ Yahoo Finance
2. Chờ ~5-10 giây để AI phân tích
3. Đọc báo cáo đánh giá

### Đánh giá thường bao gồm:
- Thị trường VN đang ở đâu? (tích cực/tiêu cực/trung tính)
-/crypto: BTC/ETH/SOL xu hướng nào?
- Vàng & dầu: có biến động gì không?  
- Khuyến nghị short-term cho portfolio

💡 *Tính năng này được tối ưu để luôn dùng dữ liệu FRESH — hệ thống tự refresh cache trước khi generate.*

---

## ⭐ TAB 6: WATCHLIST (DANH SÁCH THEO DÕI)

Quản lý danh sách mã cổ phiếu/yêu thích và xem giá real-time.

### Thêm mã vào watchlist:
1. Mở tab Watchlist
2. Nhập symbol vào ô "New Symbol": `VNM`, `HPG`, `FPT`... 
3. Click "Add to Watchlist"

### Xem giá real-time:
Watchlist hiển thị tự động các thông tin cho từng mã:
```
- VNM (Vietnam Dairy)  
  📈 57.500đ (+1.23%) 

- HPG (Hoa Phat Group)
  📉 28.900đ (-0.85%)

- BTC (Bitcoin)
  📈 $84,250 (+2.5%)
```

### Xóa khỏi watchlist:
1. Click nút "Remove" bên cạnh mã muốn xóa  
2. Xác nhận → biến mất khỏi danh sách

💡 **Mẹo hay:** Watchlist hoạt động như một "dashboard mini" — mở lên là thấy giá + % thay đổi của tất cả codes bạn quan tâm mà không cần vào từng tab Analysis.

---

## 🖥️ DÙNG QUA CLI (COMMAND LINE)

Nếu thích làm việc terminal hơn, Jarvis Hub có đầy đủ tính năng qua command-line:

### Các lệnh cơ bản:
```bash
cd ~/jarvis-hub

# Chạy briefing tin tức buổi sáng
python cli.py briefing --type morning

# Phân tích 1 mã
python cli.py analyze VNM

# Xem giá watchlist realtime
python cli.py watch list

# Tra cứu thuật ngữ
python cli.py search RSI

# Kiểm tra sức khỏe hệ thống
python cli.py doctor
```

> 💡 Gợi ý: Nếu thường dùng, hãy tạo alias trong `~/.zshrc`:  
> `alias jarvis="cd ~/jarvis-hub && python cli.py"`

---

## 🤖 TÍCH HỢP VỚI HERMES AGENT (NÂNG CAO)

Jarvis Hub hỗ trợ **tự động hoá** qua Hermes cron jobs:

### Auto-briefing mỗi sáng (6h18 AM):
```bash
jarvis cron job create \
   --prompt "Run jarvis briefing và gửi kết quả lên Telegram" \
   --schedule "0 23 * * *" \      # 06:18 GMT+7
   --name jarvis-morning-briefing
```

### Auto-analysis mã yêu thích:
Bạn có thể create nhiều cron jobs để analysis tự động các mã quan trọng mỗi phiên trading.

---

## 📋 CHECKLIST SỬ DỤNG HÀNG NGÀY

### Buổi sáng (khi mở máy):
1. ✅ Mở Jarvis Hub dashboard (http://localhost:8100)
2. 👀 Nhìn News Feed — nắm tin tức nóng nhất trong ngày
3. 🔍 Check Watchlist — xem giá các mã mình quan tâm đã biến động ra sao
4. 📊 Market Evaluation — đọc đánh giá tổng quan thị trường

### Khi muốn phân tích sâu một mã:
1. ✅ Vào tab Analysis → nhập symbol (vd: `VNM`)
2. ⏳ Chờ 5-15s cho fetch + LLM generate
3. 📖 Đọc báo cáo: xu hướng, S/R levels, recommendation
4. 💡 Click save analysis nếu muốn lưu lại (hoặc nhờ AI generate KB entry)

### Buổi tối (tổng kết ngày):
1. ✅ Chạy `jarvis briefing --type evening` để có summary ngày hôm nay
2. 👀 Check Daily Snapshots — xem snapshot tự động đã được tạo chưa

---

## ❓ CÂU HỎI THƯỜNG GẶP

### Q: Tại sao giá hiển thị khác với trên website?
**A:** Jarvis Hub lấy dữ liệu từ Yahoo Finance API — có thể chậm 15-30 phút so với real-time. Đây là giới hạn của free API, không phải lỗi hệ thống.

### Q: LLM analysis report hơi dài, có cách nào ngắn gọn hơn?
**A:** Report được AI generate tự động theo prompt template chuẩn (Support/Resistance, TA Signals, Recommendation, Catalysts). Để tweak prompt, edit file `app.py` ở phần system prompt (~dòng 377-415).

### Q: Tại sao lần đầu phân tích chậm ~15 giây?
**A:** Jarvis Hub đang fetch dữ liệu real-time từ Yahoo Finance và gọi Ollama LLM. Lần sau (cùng symbol) sẽ chỉ cache → nhanh hơn ~10x.

### Q: Có thể xuất báo cáo ra file/PDF được không?
**A:** Hiện tại chưa có tính năng export, nhưng bạn có thể copy-paste content từ modal hoặc CLI output rồi lưu vào text file riêng.

### Q: Dữ liệu tự động cập nhật lúc nào?
**A:** 
- Khi cache stale (>12 tiếng hoặc qua ngày mới)
- Tự động trigger khi mở tab Analysis/Evaluation  
- Manual: kill server và start lại (`python app.py`)

---

## 🔧 troubleshooting cơ bản

| Vấn đề | Cách fix |
|--------|----------|
| Không load được web dashboard | Chạy `jarvis doctor` để check Ollama + DB status |
| LLM analysis không xuất kết quả | Đảm bảo Ollama đang chạy: `ollama serve &` |
| RSS tin tức không hiển thị | Check internet, hoặc đổi source trong config.yaml |
| Port 8100 bị chiếm bởi process khác | `lsof -t -i :8100 \| xargs kill -9` rồi start lại |

---

## 📞 HỖ TRỢ & CẬP NHẬT

Tài liệu này sẽ được update liên tục khi Jarvis Hub có tính năng mới.  
Cập nhật lần cuối: **2026-05-22**

---

*Chúc bạn giao dịch hiệu quả! 🚀📈*
