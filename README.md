# Affiliate Hot Tool

Prototype Python cho page đồ gia dụng: chọn sản phẩm hot, tạo nội dung đăng Facebook, và lưu draft để bạn duyệt trước khi đăng.

## Vì sao bản này không tự bấm đăng Facebook?

Với Facebook Page, đường chính thống để đăng tự động là Meta Graph API và quyền publish/page management. Nếu tài khoản Meta Developer của bạn đang bị chặn thì tool không nên lách bằng automation bấm nút đăng trong giao diện Facebook, vì dễ vi phạm điều khoản và dễ khóa tài khoản. Bản này tạo draft và mở Page để bạn tự dán/đăng.

## Vì sao Shopee dùng CSV/manual trước?

Bạn nói không có Shopee Open API, chỉ có tài khoản affiliate. Trang `https://affiliate.shopee.vn/offer/product_offer` thường cần đăng nhập, nên tool không nên lưu mật khẩu hoặc scrape trái phép. Cách test ổn nhất:

1. Vào Shopee Affiliate bằng browser của bạn.
2. Tìm nhóm đồ gia dụng/hàng hot trong tuần.
3. Copy link affiliate và thông tin sản phẩm.
4. Chạy lệnh `post-manual` bên dưới để tạo bài đăng đầu tiên.

## Chạy thử xếp hạng 5-7 sản phẩm

```powershell
cd C:\Users\Nam\Documents\Codex\2026-06-17\gi-s-t-i-c-1\outputs\affiliate_hot_tool
python -m affiliate_tool.cli rank --csv data\sample_products.csv --limit 7
```

## Dùng Groq để phân tích top sản phẩm

Tạo file `.env` từ `.env.example`, sau đó điền:

```env
GROQ_API_KEY=gsk_xxx
GROQ_MODEL=llama-3.3-70b-versatile
```

Chạy:

```powershell
python -m affiliate_tool.cli rank --csv data\sample_products.csv --limit 7 --use-groq
```

Nếu Groq hết token, sai key, quá rate limit, mất mạng, hoặc response lỗi, tool sẽ tự chuyển về scoring nội bộ dựa trên các tín hiệu có sẵn trong CSV: bán gần đây, rating, review, giảm giá, hoa hồng.

## Tạo thư mục nội dung mỗi ngày

Command `daily` sẽ tạo thư mục theo ngày, bên trong mỗi sản phẩm có:

- `post.txt`: bài viết Facebook đề xuất.
- `product.json`: điểm số, lý do chọn, link affiliate, metadata ảnh/video tìm được.
- `image_*.jpg/png/webp`: ảnh tải được.
- `video_*.mp4`: video tải được nếu CSV/link công khai có video.

```powershell
python -m affiliate_tool.cli daily `
  --csv data\sample_products.csv `
  --limit 7 `
  --use-groq `
  --output-root daily_out
```

Test không tải ảnh/video:

```powershell
python -m affiliate_tool.cli daily `
  --csv data\sample_products.csv `
  --limit 7 `
  --use-groq `
  --no-download-assets `
  --output-root daily_out
```

Output sẽ có dạng:

```text
daily_out/
  2026-06-17/
    summary.json
    01-ten-san-pham/
      post.txt
      product.json
      image_1.jpg
      video_1.mp4
```

## CSV nên có những cột nào?

Tối thiểu:

```text
title,url,price,original_price,sold_week,rating,review_count,commission_rate,shop_name,category
```

Nếu bạn copy/export được media từ Shopee Affiliate hoặc từ trang sản phẩm, thêm:

```text
image_url,image_urls,video_url,video_urls,description
```

`image_urls` và `video_urls` có thể ngăn cách bằng dấu `;` hoặc `|`.

## Test tạo 1 bài đăng từ link Shopee Affiliate

Thay URL bằng link affiliate bạn lấy được từ `product_offer`.

```powershell
cd C:\Users\Nam\Documents\Codex\2026-06-17\gi-s-t-i-c-1\outputs\affiliate_hot_tool
python -m affiliate_tool.cli post-manual `
  --title "Máy xay sinh tố mini 2 cối cho gia đình" `
  --url "https://shopee.vn/your-affiliate-product-link" `
  --price 199000 `
  --original-price 299000 `
  --sold-week 420 `
  --rating 4.8 `
  --review-count 1830 `
  --commission-rate 8.5 `
  --shop-name "Gia Dụng Xanh"
```

Draft sẽ nằm ở:

```text
out/facebook_post.txt
```

## Hướng nâng cấp hằng ngày

- Nguồn sản phẩm: CSV export/copy từ Shopee Affiliate, Google Sheet, hoặc API hợp lệ của bên thứ ba.
- Chấm điểm: Groq phân tích trước nếu còn quota; fallback bằng scoring nội bộ khi Groq lỗi/hết token.
- Media: ưu tiên cột ảnh/video trong CSV; sau đó thử đọc metadata công khai từ link sản phẩm. Shopee có thể không trả video nếu nội dung cần đăng nhập hoặc render bằng app.
- Lịch chạy: Windows Task Scheduler gọi command `rank`, chọn top 5-7 rồi tạo draft.
- Đăng Facebook: khi có Meta Developer hợp lệ thì thêm adapter Graph API; khi chưa có thì giữ manual approval.
