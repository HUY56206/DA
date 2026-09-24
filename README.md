# META Realtime Dashboard – Ứng dụng Real-Time Updates

Ứng dụng web trực tuyến (truy cập mọi lúc) áp dụng kỹ thuật **Real-Time Updates** cho bài môn **Phân tích & Trực quan hóa Dữ liệu** (PTDLNC).

## Tính năng

- **Real-Time Updates**: app tự cập nhật định kỳ (5–120 giây, tùy chỉnh) qua `streamlit-autorefresh`; metrics và biểu đồ làm mới ngay trên trang — không cần bấm refresh.
- **Biểu đồ trượt theo thời gian**: ở chế độ *mô phỏng tick real-time*, mỗi lần refresh app tự thêm 1 tick và chỉ hiển thị 90 nốt gần nhất → biểu đồ **dịch chuyển sang phải theo thời gian thực** (sliding window), kèm chấm sáng đỏ cho giá mới nhất.
- **Dữ liệu thật**: lịch sử OHLCV của `META` (hoặc 7 mã: AAPL, MSFT, GOOGL, AMZN, NVDA, TSLA) lấy trực tiếp từ **Yahoo Finance**, không cần API key.
- **Hàm lượng khoa học**:
  - Biểu đồ chính sáng tạo: line chia đoạn **xanh/đỏ theo trend** + marker gradient RdYlGn (lợi suất ngày) + vùng lấp đầy + volume.
  - Phân tích kỹ thuật: **RSI(14)**, **MACD (12,26,9)**, **Bollinger Bands (SMA20 ± 2σ)**, SMA 20/50.
  - Metrics: lợi suất 1 năm, **độ biến động annualized (Vol20)**, **Sharpe ratio**, **Maximum Drawdown**, khối lượng.
  - **Heatmap tương quan** lợi suất giữa các cổ phiếu trong danh mục.

## Cấu trúc repo

```
meta-realtime-app/
├── app.py                 # Ứng dụng Streamlit chính
├── requirements.txt       # Các thư viện cần thiết
├── .streamlit/config.toml # Theme
└── .gitignore
```

## Chạy local (kiểm tra trước khi deploy)

```bash
cd meta-realtime-app
pip install -r requirements.txt
streamlit run app.py
```

Mở trình duyệt tại `http://localhost:8501`.

## Deploy miễn phí (truy cập 24/7)

### Bước 1 – Tạo repo GitHub (private hoặc public)

1. Lên https://github.com → **New repository** → tên `meta-realtime-app` → chọn **Private** (hoặc Public) → **Create repository**.
2. Push code lên:

```bash
cd meta-realtime-app
git init
git add .
git commit -m "Realtime dashboard META"
git branch -M main
git remote add origin https://github.com/<your-username>/meta-realtime-app.git
git push -u origin main
```

### Bước 2 – Deploy lên Streamlit Community Cloud (miễn phí)

1. Vào https://streamlit.io/cloud → **Sign in with GitHub** (cấp quyền truy cập repo bạn vừa tạo — hỗ trợ cả repo **private**).
2. Bấm **New app**:
   - Repository: `meta-realtime-app`
   - Branch: `main`
   - Main file path: `app.py`
3. Bấm **Deploy**. Sau ~1–2 phút app online.

Link truy cập: `https://<your-username>-meta-realtime-app.streamlit.app`

> App Streamlit Community Cloud miễn phí, chạy **24/7**, không cần thẻ tín dụng.
> Nếu app ngủ sau một thời gian idle, chỉ cần mở lại link là nó tự khởi động lại.

### Thay Heroku (không bắt buộc)

Heroku đã bỏ free tier (cần thẻ tín dụng) nên ưu tiên Streamlit Cloud. Cấu trúc code tương tự có thể chạy trên Render (free tier) nếu cần.

## Lưu ý kỹ thuật về "Real-Time Updates"

- Cơ chế: `st_autorefresh(interval, key)` khiến Streamlit **chạy lại toàn bộ script** mỗi `interval` giây (tương đương vòng lặp UI thread trong Dash context, nhưng đúng chuẩn Streamlit). Dữ liệu được cache bằng `@st.cache_data(ttl=30)` nên mỗi lần rerun chỉ fetch lại khi hết TTL.
- Muốn realtime **thực sự** (tick tới từng giây) cần WebSocket (ví dụ Alpaca, Binance, Polygon). Ở bài này, tự cập nhật vài chục giây/lần là phù hợp ngữ cảnh "Real-Time Updates" trong slide 3.
- Hệ số tương quan dùng `pct_change()` (lợi suất hàng ngày) trước khi `corr()` để tránh tương quan giả do xu hướng giá.