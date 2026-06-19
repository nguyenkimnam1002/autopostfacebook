# Giao diện localhost

Chạy server:

```powershell
cd D:\WORK_2\hayho\affiliate_hot_tool
python -m affiliate_tool.cli web --host 127.0.0.1 --port 8001
```

Mở:

```text
http://127.0.0.1:8001/affiliate_hot_tool
```

Nếu port 8001 bận, đổi sang port khác:

```powershell
python -m affiliate_tool.cli web --host 127.0.0.1 --port 8010
```

Giao diện hỗ trợ:

- Tự tìm sản phẩm hot từ Shopee public search theo keyword đồ gia dụng.
- Upload CSV sản phẩm.
- Bật Groq để phân tích, lỗi/hết quota thì fallback scoring local.
- Chọn số sản phẩm top.
- Xem bài viết Facebook đề xuất cho từng link affiliate.
- Export thư mục theo ngày vào `daily_out` hoặc thư mục bạn nhập.
- Tùy chọn tải ảnh/video khi export.

CSV tối thiểu cần:

```text
title,url,price,original_price,sold_week,rating,review_count,commission_rate,shop_name,category
```

Nếu có media, thêm:

```text
image_url,image_urls,video_url,video_urls,description
```

## Khi Shopee trả lỗi 403

Shopee có thể chặn request public nếu không có phiên đăng nhập. Khi đó tạo file `.env` trong thư mục tool và thêm:

```env
SHOPEE_COOKIE=your_cookie_from_logged_in_browser
```

Cookie lấy từ browser bạn đã đăng nhập Shopee/Shopee Affiliate. Đây là dữ liệu nhạy cảm, chỉ lưu trên máy local của bạn.
