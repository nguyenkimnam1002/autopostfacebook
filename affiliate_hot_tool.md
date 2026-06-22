# Affiliate Hot Tool

## 1. Muc dich

Affiliate Hot Tool la bo cong cu local dung de:

- Doc danh sach san pham tu CSV hoac tu Shopee search.
- Cham diem va chon san pham "hot".
- Bo sung anh/video san pham neu co the lay duoc.
- Tao noi dung dang Facebook.
- Dang bai len Fanpage, dang Story, dang Reels bang Meta Graph API.
- Luu archive theo ngay de tai lai va dang lai sau nay.

Tool chay local tren may Windows, giao dien web phuc vu o `http://127.0.0.1:<port>/affiliate_hot_tool`.

## 2. Thanh phan chinh

- `affiliate_tool/web_app.py`
  Server web localhost, HTML/JS giao dien, toan bo API backend cho giao dien.
- `affiliate_tool/cli.py`
  Diem vao command line: `rank`, `discover`, `daily`, `daily-discover`, `post-manual`, `web`.
- `affiliate_tool/discovery.py`
  Tim san pham Shopee, parse keyword, lay media san pham qua API Shopee PDP.
- `affiliate_tool/loaders.py`
  Doc CSV va map cot du lieu vao model san pham.
- `affiliate_tool/scoring.py`
  Cham diem local.
- `affiliate_tool/groq_analyzer.py`
  Cham diem bang Groq, neu co API key va bat tuy chon.
- `affiliate_tool/posting.py`
  Tao noi dung bai dang Facebook va title cho Reels.
- `affiliate_tool/facebook_auth.py`
  OAuth Facebook, doi User Token sang long-lived Page token, kiem tra scope.
- `affiliate_tool/facebook_graph.py`
  Dang bai, Story, Reels len Facebook bang Graph API.
- `affiliate_tool/exporter.py`
  Xuat thu muc archive theo ngay, luu `post.txt`, `product.json`, anh, video, `summary.json`.
- `affiliate_tool/shopee_session.py`
  Mo Chrome debug profile rieng, doc cookie, goi Shopee trong phien da dang nhap.
- `chrome_extension/`
  Extension ho tro fallback cho mot so thao tac frontend va media/page automation cu.

## 3. Kieu du lieu dau vao

### 3.1 CSV

Cot toi thieu:

```text
title,url,price,original_price,sold_week,rating,review_count,commission_rate,shop_name,category
```

Cot media neu co:

```text
image_url,image_urls,video_url,video_urls,description,source_url,product_id,sold_month
```

`image_urls` va `video_urls` co the tach bang `;` hoac `|`.

### 3.2 Tim truc tiep tu Shopee

Tool co the tu tim san pham tu keyword qua Shopee search. Nguon nay dung de lay ung vien nhanh, sau do cham diem va enrich media tiep.

## 4. Cac command CLI

### 4.1 `rank`

Dung de doc CSV va cham diem top san pham.

```powershell
python -m affiliate_tool.cli rank --csv data\sample_products.csv --limit 7
```

### 4.2 `discover`

Dung de tim san pham tu Shopee search theo keyword.

```powershell
python -m affiliate_tool.cli discover --keywords "ban hoc, ghe hoc sinh" --limit 7
```

### 4.3 `daily`

Doc CSV, cham diem, xuat archive theo ngay.

```powershell
python -m affiliate_tool.cli daily --csv data\sample_products.csv --limit 7 --output-root out
```

### 4.4 `daily-discover`

Tim san pham tu Shopee search, cham diem, roi xuat archive.

### 4.5 `post-manual`

Tao nhanh 1 draft bai dang tu command line.

### 4.6 `web`

Mo giao dien localhost.

```powershell
python -m affiliate_tool.cli web --host 127.0.0.1 --port 8001
```

## 5. Cau hinh can thiet

### 5.1 `.env`

Co the dung:

```env
GROQ_API_KEY=
GROQ_MODEL=
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
FACEBOOK_PAGE_ID=
FACEBOOK_PAGE_ACCESS_TOKEN=
FACEBOOK_REDIRECT_URI=
META_GRAPH_VERSION=v25.0
SHOPEE_COOKIE=
```

### 5.2 File du lieu runtime

- `data/facebook_auth.json`
  Chua Page token da doi thanh cong.
- `data/facebook_oauth_state.json`
  State OAuth tam thoi.
- `data/facebook_oauth_error.json`
  Loi OAuth neu co.

## 6. Giao dien web va luong su dung

## 6.1 Luong tong quat

1. Chon nguon san pham.
2. Kiem tra san pham hot.
3. Tool cham diem va hien danh sach.
4. Tool enrich anh/video neu co the.
5. Tick cac san pham can dang.
6. Chon mot trong ba kieu dang:
   `Dang bai len Fanpage`, `Dang tin Anh/Video`, `Dang thuoc phim`.
7. Neu can, xuat archive theo ngay va tai lai san pham cu.

## 6.2 Cac khu vuc chinh tren web

### A. Nguon du lieu

- Upload CSV.
- Hoac dung nguon discover tu Shopee search theo keyword.
- Chon co su dung Groq hay khong.
- Chon so luong top san pham.
- Chon co tai anh/video khi kiem tra hay khong.

### B. Shopee session

- `Mo Chrome login Shopee`
  Mo profile Chrome rieng de dang nhap Shopee.
- `Lay cookie Shopee`
  Doc cookie tu profile Chrome debug da dang nhap.
- Muc dich:
  dung de enrich media san pham khi Shopee can phien dang nhap.

### C. Facebook Graph

- `Ket noi Facebook`
  Mo OAuth login.
- `Kiem tra token`
  Doc trang thai da ket noi hay chua.
- O `Token lau dai`
  Dan User Token vao va bam `Dung token lau dai`.
- Muc dich:
  doi sang Page token lau dai, tranh het han token khi dang.

### D. Khu dang bai

- `Dang bai len Fanpage`
  Dang bai feed.
- `Dang tin Anh/Video`
  Dang Story.
- `Dang thuoc phim`
  Dang Reels.
- `Tu bam Dang sau khi dien noi dung`
  Dung cho fallback automation cu khi khong dung Graph API.

### E. Khu archive

- Chuyen qua `San pham cu`.
- Chon ngay.
- Bam `Tai san pham cu`.
- Tool load du lieu cu, media local, va enrich bo sung neu can.

## 7. Luong xu ly san pham

## 7.1 Kiem tra san pham hot

API: `POST /affiliate_hot_tool/api/analyze`

Backend:

1. Doc form.
2. Xac dinh nguon:
   `csv`, `bulk_csv`, hoac `discover`.
3. Nap danh sach san pham.
4. Cham diem bang Groq neu bat.
5. Neu Groq loi thi fallback scoring local.
6. Tra ve danh sach da rank.

Neu bat `export`, backend se goi `export_daily_package()` de xuat archive cung luc.

## 7.2 Kiem tra san pham tu extension

API: `POST /affiliate_hot_tool/api/analyze-products`

Dung khi danh sach san pham duoc extension/gui frontend chuan bi san.

## 7.3 Enrich anh/video

API: `POST /affiliate_hot_tool/api/enrich-media`

Backend:

1. Nhan danh sach san pham tu frontend.
2. Kiem tra co Shopee session hay cookie khong.
3. Goi `enrich_products_with_media()`.
4. Lay media tu API Shopee PDP `get_pc`.
5. Cap nhat `image_url`, `image_urls`, `video_url`, `video_urls`.
6. Tra lai danh sach da enrich.

Frontend tu dong goi enrich sau khi:

- phan tich san pham moi xong.
- tai san pham cu xong.

## 8. Luong Facebook

## 8.1 Xac thuc Facebook

### OAuth flow

API:

- `POST /affiliate_hot_tool/api/facebook-auth-start`
- `POST /affiliate_hot_tool/api/facebook-auth-status`
- `GET /affiliate_hot_tool/facebook/callback`

Luong:

1. Web mo login URL.
2. User dang nhap va cap quyen.
3. Facebook goi callback.
4. Tool doi code lay user token.
5. Tool doi user token sang page token.
6. Luu `data/facebook_auth.json`.

### Dung User Token thu cong

API: `POST /affiliate_hot_tool/api/facebook-token-exchange`

Luong:

1. User dan User Token vao textarea.
2. Backend doi sang long-lived user token.
3. Backend lay page token lau dai.
4. Backend kiem tra scope.
5. Backend tra thong bao token du/thieu quyen nao.

## 8.2 Dang bai len Fanpage

API: `POST /affiliate_hot_tool/api/facebook-queue`

Luật:

- Toi da 5 san pham moi lan.
- Neu Graph API san sang, dang tung bai mot.
- Co delay giua cac bai de tranh spam.

Media flow:

1. Neu co video:
   uu tien dang video.
2. Neu video loi:
   fallback sang anh.
3. Neu anh loi:
   fallback sang bai link/feed.
4. Sau khi dang:
   tool thu comment link mua hang.
5. Neu con anh phu hop:
   tool thu comment them anh phu.

Noi dung bai dang:

- Bat dau thang bang ten san pham.
- Co `Shop`.
- Co `Diem noi bat`.
- Co `Link san pham`.
- Khong public gia.

## 8.3 Dang Story

API: `POST /affiliate_hot_tool/api/facebook-story-queue`

Luật:

- Toi da 5 san pham moi lan.
- Can Graph API.
- Neu co video thi uu tien video.
- Neu khong co video thi dung anh dau tien.
- Neu khong co media thi khong dang duoc.

Ghi chu:

- Story API khong ho tro link sticker clickable chinh thuc trong flow nay.
- Tool chi co the canh bao va giu affiliate link trong warning/noi bo.

## 8.4 Dang Reels

API: `POST /affiliate_hot_tool/api/facebook-reel-queue`

Luật:

- Toi da 5 san pham moi lan.
- Can Graph API.
- Chi nhan san pham co video.
- Neu khong co video thi backend tu choi.

Luong:

1. `upload_phase=start` toi endpoint `video_reels`.
2. Upload video qua `upload_url`.
3. `upload_phase=finish`.
4. Publish Reels.

Title Reels:

- Dung truc tiep ten san pham.

Description Reels:

- Dung cung format voi bai dang Facebook, khong co gia.

## 9. Archive va tai san pham cu

## 9.1 Xuat archive

API:

- `POST /affiliate_hot_tool/api/export`
- `POST /affiliate_hot_tool/api/export-products`

Moi ngay tool tao:

```text
out/
  YYYY-MM-DD/
    summary.json
    <product_id>/
      post.txt
      product.json
      image_1.jpg
      video_1.mp4
```

Trong do:

- `summary.json`
  Tong hop rank, score, duong dan thu muc, danh sach file media tai duoc.
- `product.json`
  Metadata san pham, media detect duoc, diem, ly do.
- `post.txt`
  Noi dung bai dang da tao tai thoi diem export.

## 9.2 Tai san pham cu

API:

- `POST /affiliate_hot_tool/api/archive-dates`
- `POST /affiliate_hot_tool/api/archive-products`
- `GET /affiliate_hot_tool/api/archive-media`

Luong:

1. Frontend lay danh sach ngay co archive.
2. User chon ngay.
3. Backend doc `summary.json` va tung `product.json`.
4. Backend khoi phuc media tu:
   URL detect trong JSON, hoac file local trong thu muc san pham.
5. Neu van thieu media:
   frontend tu enrich lai qua Shopee session.

`/api/archive-media` dung de browser xem file local archive qua HTTP an toan, thay vi doc truc tiep duong dan Windows.

## 10. Luong media

Nguon media uu tien:

1. Media da co tren item hien tai.
2. Media detect tu Shopee PDP API.
3. Media local da luu trong archive.
4. Enrich lai neu item cu chua co media.

Bo loc media:

- Uu tien file anh/video san pham that.
- Loai bot mot so link rac, null, svg, file khong hop le.

Frontend hien thi:

- Neu co `video_url`: show video thumb.
- Neu co `image_url`: show image thumb.
- Neu khong co gi: hien `Chua co media`.

## 11. Response va progress tren frontend

Frontend co:

- progress bar cho dang bai, Story, Reels.
- status box de hien warning, loi, thanh cong.
- render danh sach san pham co checkbox de chon.

Khi dang Graph API:

- Frontend dang tung san pham mot.
- Moi lan dang xong se update phan tram.
- Giua cac bai co countdown cho de tranh burst spam.

## 12. Cac API chinh

### Shopee va ranking

- `POST /api/analyze`
- `POST /api/export`
- `POST /api/analyze-products`
- `POST /api/enrich-media`
- `POST /api/open-shopee-login`
- `POST /api/open-default-chrome`
- `POST /api/read-shopee-cookie`
- `POST /api/auto-detect-cookie`

### Facebook

- `POST /api/facebook-auth-start`
- `POST /api/facebook-auth-status`
- `POST /api/facebook-token-exchange`
- `GET /facebook/callback`
- `POST /api/facebook-queue`
- `POST /api/facebook-story-queue`
- `POST /api/facebook-reel-queue`

### Archive

- `POST /api/archive-dates`
- `POST /api/archive-products`
- `GET /api/archive-media`
- `POST /api/export-products`

### Khac

- `GET /health`

Tat ca cac route tren deu nam duoi prefix:

```text
/affiliate_hot_tool
```

## 13. Thu muc va file sinh ra

- `out/`
  Archive theo ngay.
- `web_uploads/`
  CSV user upload tu giao dien web.
- `data/facebook_auth.json`
  Token Page sau khi ket noi thanh cong.
- `server.pid`
  PID server neu script start/stop co dung.

## 14. Gioi han va dieu kien de chuc nang chay

- Dang bai/Story/Reels can Facebook token hop le.
- Story va Reels can media.
- Reels bat buoc phai co video.
- Media Shopee co the can dang nhap de lay duoc day du.
- Neu Groq khong co key, het quota, loi mang:
  tool se fallback scoring local.
- Cac bai `post.txt` da export truoc do la ban chup lich su:
  khong tu dong doi noi dung khi format moi thay doi.

## 15. Script chay nhanh

- `start_server.bat`
  Mo server localhost.
- `stop_server.bat`
  Dung server.
- `start_default_chrome_debug.bat`
  Mo Chrome debug fallback.

## 16. Cach van hanh de xuat

1. Mo server web.
2. Mo Chrome login Shopee neu can enrich media.
3. Ket noi Facebook hoac dan User Token doi sang token lau dai.
4. Upload CSV hoac discover keyword.
5. Bam `Kiem tra san pham HOT`.
6. Cho tool enrich media.
7. Tick san pham can dang.
8. Chon dang bai, Story, hoac Reels.
9. Neu can luu lich su, export ra `out`.
10. Khi can dang lai, vao `San pham cu` va tai theo ngay.

## 17. Muc tieu cua he thong

Muc tieu cua tool khong phai la crawl dai tra hay automation mang tinh ne tranh he thong, ma la:

- tang toc quy trinh chon hang hot,
- giup co media de nhin nhanh,
- tao noi dung dang nhat quan,
- va dang len Facebook bang luong hop le, de user co the van hanh tren may local moi ngay.
