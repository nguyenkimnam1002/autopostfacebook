# Affiliate Hot Tool

Affiliate Hot Tool là ứng dụng chạy local trên Windows để chọn sản phẩm Shopee Affiliate, lấy ảnh/video sản phẩm, tạo nội dung bán hàng và đăng lên Facebook Page bằng Meta Graph API.

Giao diện web mặc định:

```text
http://127.0.0.1:8001/affiliate_hot_tool
```

## 1. Chức năng chính

- Upload file CSV sản phẩm/link hàng loạt từ Shopee Affiliate.
- Đọc các cột sản phẩm phổ biến: mã sản phẩm, tên sản phẩm, giá, lượt bán, shop, hoa hồng, link sản phẩm, link ưu đãi/affiliate.
- Chấm điểm và sắp xếp sản phẩm hot bằng scoring local.
- Có thể dùng Groq để phân tích/chấm điểm nếu có `GROQ_API_KEY`; khi Groq lỗi hoặc hết quota thì tự fallback về scoring local.
- Mở Chrome profile riêng để đăng nhập Shopee và lấy cookie Shopee.
- Dùng cookie Shopee để enrich ảnh/video sản phẩm từ Shopee.
- Hiển thị danh sách sản phẩm có checkbox để chọn sản phẩm cần đăng.
- Tạo nội dung bài đăng Facebook cho từng sản phẩm.
- Đăng bài lên Fanpage bằng Meta Graph API.
- Đăng bài 4 ảnh cho sản phẩm có nhiều ảnh.
- Đăng tin ảnh/video lên Facebook Page Story.
- Đăng tin qua giao diện Facebook Business Story Composer khi cần thử gắn link web.
- Đăng thước phim/Reels cho sản phẩm có video.
- Comment link mua hàng/affiliate dưới bài đăng khi token có quyền phù hợp.
- Lưu archive sản phẩm theo ngày vào `out/`, gồm `summary.json`, `product.json`, `post.txt`, ảnh và video nếu tải được.
- Load lại sản phẩm cũ từ archive để đăng lại hoặc kiểm tra lại media.

## 2. Khởi động và dừng ứng dụng

### Cách nhanh bằng file batch

Chạy:

```powershell
.\start_server.bat
```

Script sẽ:

- chạy server tại `127.0.0.1:8001`,
- ghi PID vào `server.pid`,
- mở trình duyệt vào `http://127.0.0.1:8001/affiliate_hot_tool`.

Dừng ứng dụng:

```powershell
.\stop_server.bat
```

Script sẽ ưu tiên dừng PID trong `server.pid`; nếu không có PID thì tìm process đang listen port `8001` để dừng.

### Cách chạy thủ công

```powershell
python -m affiliate_tool.cli web --host 127.0.0.1 --port 8001
```

Nếu muốn đổi port:

```powershell
python -m affiliate_tool.cli web --host 127.0.0.1 --port 8002
```

Khi chạy thủ công, dừng bằng `Ctrl+C` ở cửa sổ terminal đang chạy server.

## 3. Thiết lập ứng dụng

### 3.1. Chuẩn bị `.env`

Copy `.env.example` thành `.env`, sau đó điền các biến cần dùng:

```env
FACEBOOK_PAGE_URL=https://www.facebook.com/your-page
META_GRAPH_VERSION=v25.0
FACEBOOK_PAGE_ID=
FACEBOOK_PAGE_ACCESS_TOKEN=
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
FACEBOOK_LOGIN_CONFIG_ID=
FACEBOOK_REDIRECT_URI=

GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile

SHOPEE_COOKIE=
```

Các biến quan trọng:

- `FACEBOOK_APP_ID`: App ID của app trong Meta for Developers.
- `FACEBOOK_APP_SECRET`: App Secret của app trong Meta for Developers.
- `FACEBOOK_PAGE_ID`: ID Fanpage muốn đăng. Nên điền nếu tài khoản quản lý nhiều Page.
- `FACEBOOK_PAGE_ACCESS_TOKEN`: Page token có sẵn. Có thể để trống nếu dùng nút kết nối/token exchange trên web.
- `FACEBOOK_REDIRECT_URI`: callback OAuth. Nếu để trống, tool dùng mặc định `http://127.0.0.1:8001/affiliate_hot_tool/facebook/callback`.
- `FACEBOOK_LOGIN_CONFIG_ID`: dùng khi app Meta cấu hình Facebook Login for Business.
- `GROQ_API_KEY`: tùy chọn, dùng để phân tích sản phẩm bằng AI.
- `SHOPEE_COOKIE`: tùy chọn, chỉ cần khi không dùng nút lấy cookie Shopee từ Chrome.

Không commit `.env`, `data/facebook_auth.json`, cookie hoặc token thật lên git.

### 3.2. Tạo tài khoản/app Meta Developer

1. Vào `https://developers.facebook.com/`.
2. Đăng nhập bằng tài khoản Facebook có quyền quản lý Fanpage.
3. Tạo app mới trong Meta for Developers.
4. Chọn loại app phù hợp với nhu cầu quản lý Page/Facebook Login.
5. Vào phần cài đặt app để lấy:
   - `App ID` -> điền vào `FACEBOOK_APP_ID`;
   - `App Secret` -> điền vào `FACEBOOK_APP_SECRET`.
6. Thêm sản phẩm Facebook Login hoặc Facebook Login for Business nếu app yêu cầu.
7. Cấu hình OAuth Redirect URI trùng với URL callback của tool:

```text
http://127.0.0.1:8001/affiliate_hot_tool/facebook/callback
```

Nếu dùng tunnel như ngrok để Meta gọi callback, đặt URL public đó vào `FACEBOOK_REDIRECT_URI`, ví dụ:

```env
FACEBOOK_REDIRECT_URI=https://your-ngrok-domain/affiliate_hot_tool/facebook/callback
```

### 3.3. Lấy User Token từ Graph API Explorer

1. Vào Graph API Explorer của Meta.
2. Chọn đúng app vừa tạo.
3. Chọn tài khoản Facebook đang quản lý Page.
4. Generate Access Token với các quyền:
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
   - `pages_manage_engagement`
5. Copy User Token vừa tạo.
6. Mở web tool, dán token vào ô `Token lâu dài`.
7. Bấm `Dùng token lâu dài`.

Tool sẽ tự:

- đổi User Token sang long-lived user token nếu có thể,
- gọi `/me/accounts` để lấy Page token,
- ưu tiên Page có ID trùng `FACEBOOK_PAGE_ID` nếu đã cấu hình,
- lưu kết quả vào `data/facebook_auth.json`,
- kiểm tra token đủ/thừa/thiếu quyền nào.

Sau đó có thể bấm `Kiểm tra token` trên giao diện để xác nhận trạng thái.

### 3.4. Kết nối Facebook bằng nút OAuth trong tool

Nếu đã cấu hình `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET` và redirect URI hợp lệ:

1. Mở web tool.
2. Bấm `Kết nối Facebook`.
3. Đăng nhập và cấp quyền cho app.
4. Khi callback chạy xong, quay lại tool.
5. Bấm `Kiểm tra token`.

Nếu OAuth bị chặn hoặc app chưa được duyệt quyền, dùng cách dán User Token từ Graph API Explorer ở mục trên.

### 3.5. Thiết lập Shopee session/cookie

Tool không lưu mật khẩu Shopee. Cách dùng khuyến nghị:

1. Mở web tool.
2. Bấm `Mở Chrome login Shopee`.
3. Đăng nhập Shopee/Shopee Affiliate trong cửa sổ Chrome được mở.
4. Quay lại tool và bấm `Lấy cookie Shopee`.
5. Khi trạng thái báo đã lấy cookie, bấm `Kiểm tra sản phẩm HOT` lại để tool lấy ảnh/video tốt hơn.

Thư mục `shopee_chrome_profile/` là Chrome profile riêng do tool tạo để giữ session đăng nhập Shopee. Nếu chạy trên máy khác mà chưa có thư mục này, tool vẫn chạy nhưng cần đăng nhập Shopee lại.

## 4. Cách lấy file CSV Shopee Affiliate

1. Đăng nhập Shopee Affiliate.
2. Vào khu vực lấy link sản phẩm hàng loạt hoặc danh sách offer/sản phẩm.
3. Tìm/chọn nhóm sản phẩm muốn đăng.
4. Xuất file CSV nếu Shopee có nút export/download.
5. Nếu không có nút export, copy danh sách link hàng loạt rồi lưu thành CSV theo format tương tự file trong `web_uploads/`.
6. File nên có các cột như:

```text
Mã sản phẩm,Tên sản phẩm,Giá,Lượt bán,Shop,Hoa hồng,Hoa hồng dự kiến,Link sản phẩm,Link ưu đãi
```

Tool cũng hỗ trợ format CSV chuẩn nội bộ:

```text
title,url,price,original_price,sold_week,rating,review_count,commission_rate,shop_name,category
```

Nếu có sẵn media, thêm các cột:

```text
image_url,image_urls,video_url,video_urls,description,source_url,product_id,sold_month
```

`image_urls` và `video_urls` có thể tách nhiều link bằng `;` hoặc `|`.

## 5. Cách sử dụng ứng dụng

### 5.1. Quy trình đăng sản phẩm mới

1. Chạy `.\start_server.bat`.
2. Mở `http://127.0.0.1:8001/affiliate_hot_tool`.
3. Bấm `Mở Chrome login Shopee` nếu cần lấy ảnh/video.
4. Đăng nhập Shopee trong cửa sổ Chrome được mở.
5. Bấm `Lấy cookie Shopee`.
6. Kiểm tra Facebook:
   - bấm `Kiểm tra token` nếu đã có `data/facebook_auth.json` hoặc `FACEBOOK_PAGE_ACCESS_TOKEN`;
   - hoặc bấm `Kết nối Facebook`;
   - hoặc dán User Token vào `Token lâu dài` rồi bấm `Dùng token lâu dài`.
7. Chọn file CSV ở khu `CSV link hàng loạt / sản phẩm`.
8. Bấm `Kiểm tra sản phẩm HOT`.
9. Chờ tool đọc CSV, chấm điểm, lấy ảnh/video và hiển thị danh sách.
10. Tick checkbox các sản phẩm muốn đăng.
11. Chọn kiểu đăng:
    - `Đăng bài lên Fanpage`: đăng feed, ưu tiên video nếu có; nếu video lỗi thì fallback sang ảnh/link.
    - `Đăng bài 4 ảnh`: đăng tối đa 4 ảnh đại diện, comment link mua hàng và media phụ nếu có.
    - `Đăng tin Ảnh/Video`: đăng Story bằng Graph API, ưu tiên video; nếu không có video thì dùng ảnh đầu tiên.
    - `Đăng tin giao diện FB`: mở Business Story Composer để thử đăng qua UI Facebook.
    - `Đăng thước phim`: đăng Reels, chỉ dùng sản phẩm có video.
12. Theo dõi thanh progress và status box đến khi hoàn tất.

Mỗi lần đăng nên tick tối đa 5 sản phẩm. Tool có delay giữa các bài để giảm rủi ro Facebook đánh dấu spam.

### 5.2. Upload file CSV

- Bấm chọn file ở ô `CSV link hàng loạt / sản phẩm`.
- Dùng file CSV tải từ Shopee Affiliate hoặc file đã chuẩn hóa.
- Bấm `Kiểm tra sản phẩm HOT`.
- Nếu media thiếu, đảm bảo đã đăng nhập Shopee và bấm `Lấy cookie Shopee`, sau đó kiểm tra lại.

### 5.3. Lấy cookie Shopee

- `Mở Chrome login Shopee`: mở Chrome profile riêng tại `shopee_chrome_profile/`.
- `Lấy cookie Shopee`: đọc cookie từ profile đó để backend gọi Shopee trong nền.
- `SHOPEE_COOKIE` trong `.env`: dùng khi muốn dán cookie thủ công thay vì lấy qua Chrome.

### 5.4. Điền API key Facebook/Meta

Có 3 cách:

- Cách tự động: điền `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, cấu hình redirect URI, rồi bấm `Kết nối Facebook`.
- Cách ổn định khi đã có User Token: dán User Token vào `Token lâu dài`, bấm `Dùng token lâu dài`.
- Cách thủ công: điền `FACEBOOK_PAGE_ID` và `FACEBOOK_PAGE_ACCESS_TOKEN` vào `.env`.

Khuyến nghị dùng cách `Token lâu dài` vì tool sẽ lưu Page token vào `data/facebook_auth.json` và tự kiểm tra quyền.

### 5.5. Load, checklist và đăng sản phẩm

- Sau khi phân tích CSV, bảng sản phẩm sẽ hiển thị tên, shop, hoa hồng, điểm hot, media và checkbox.
- Tick các sản phẩm muốn đăng.
- Sản phẩm không có ảnh/video vẫn có thể đăng feed dạng link, nhưng không đăng được Story/Reels.
- Reels bắt buộc có video.
- Bài 4 ảnh bắt buộc có ảnh.
- Story cần ảnh hoặc video.

### 5.6. Đăng bài, đăng tin, đăng ảnh/video

- `Đăng bài lên Fanpage`:
  - dùng Graph API;
  - nếu có video thì đăng video;
  - nếu không có video thì đăng ảnh;
  - nếu media lỗi thì fallback sang bài link;
  - comment link mua hàng nếu token có quyền `pages_manage_engagement`.

- `Đăng bài 4 ảnh`:
  - lấy tối đa 4 ảnh đầu làm ảnh chính;
  - ảnh/video còn lại có thể được comment thêm;
  - phù hợp với sản phẩm có nhiều ảnh Shopee.

- `Đăng tin Ảnh/Video`:
  - dùng Page Story API;
  - ưu tiên video;
  - nếu không có video thì dùng ảnh đầu tiên;
  - link sticker clickable không phải lúc nào cũng được Graph API hỗ trợ.

- `Đăng tin giao diện FB`:
  - mở `business.facebook.com/latest/story_composer`;
  - dùng khi muốn thử gắn link web clickable qua giao diện Meta;
  - phụ thuộc UI hiện tại của Meta và giới hạn media.

- `Đăng thước phim`:
  - dùng Graph API Reels;
  - chỉ nhận sản phẩm có video;
  - tiêu đề Reels dùng tên sản phẩm.

## 6. Sử dụng sản phẩm cũ/archive

Khi cần load lại dữ liệu đã xuất:

1. Chọn mode `Sản phẩm cũ`.
2. Chọn ngày archive.
3. Bấm tải sản phẩm cũ.
4. Tool đọc lại `out/YYYY-MM-DD/summary.json` và từng `product.json`.
5. Tick sản phẩm và đăng như sản phẩm mới.

Cấu trúc archive:

```text
out/
  YYYY-MM-DD/
    summary.json
    <product-folder>/
      product.json
      post.txt
      image_1.jpg
      video_1.mp4
```

## 7. CLI hữu ích

Rank sản phẩm từ CSV:

```powershell
python -m affiliate_tool.cli rank --csv data\sample_products.csv --limit 7
```

Rank bằng Groq trước, lỗi thì fallback local:

```powershell
python -m affiliate_tool.cli rank --csv data\sample_products.csv --limit 7 --use-groq
```

Tìm sản phẩm từ Shopee search:

```powershell
python -m affiliate_tool.cli discover --keywords "ban hoc, ghe hoc sinh" --limit 7
```

Xuất package theo ngày:

```powershell
python -m affiliate_tool.cli daily --csv data\sample_products.csv --limit 7 --output-root out
```

Tạo nhanh một draft bài đăng:

```powershell
python -m affiliate_tool.cli post-manual `
  --title "Tên sản phẩm" `
  --url "https://shopee.vn/your-affiliate-link" `
  --price 199000 `
  --sold-week 420 `
  --commission-rate 10 `
  --shop-name "Tên shop"
```

## 8. File/thư mục sinh ra khi chạy

- `server.pid`: PID server do `start_server.bat` tạo.
- `web_uploads/`: CSV upload từ giao diện web.
- `out/`: archive sản phẩm, bài viết và media.
- `data/facebook_auth.json`: Page token đã lưu sau khi kết nối Facebook.
- `data/facebook_oauth_state.json`: state tạm thời của OAuth.
- `data/facebook_oauth_error.json`: lỗi OAuth gần nhất nếu có.
- `shopee_chrome_profile/`: Chrome profile riêng để giữ session Shopee.

## 9. Lưu ý vận hành

- Không chia sẻ hoặc commit token/cookie thật.
- Token Facebook phải có đủ quyền để đăng bài và comment.
- App Meta có thể cần cấu hình/duyệt quyền tùy trạng thái app và Page.
- Shopee có thể thay đổi giao diện hoặc API nội bộ, nên chức năng lấy media có thể cần đăng nhập cookie mới.
- Nếu thiếu ảnh/video, thử đăng nhập lại Shopee rồi bấm `Lấy cookie Shopee`.
- Nếu Facebook báo token hết hạn, tạo User Token mới trong Graph API Explorer rồi bấm `Dùng token lâu dài`.
- Nếu port `8001` đang bị process khác dùng, dừng process đó hoặc chạy server bằng port khác.
