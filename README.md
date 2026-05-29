# 📚 Bộ Xử Lý & Tách File PDF Chuyên Nghiệp (PDF Splitter)

Ứng dụng Desktop chuyên nghiệp viết bằng **Python**, sử dụng giao diện hiện đại **PySide6** và công cụ render PDF tốc độ cao **PyMuPDF (fitz)**. Ứng dụng được thiết kế tối ưu cho các tác vụ số hóa tài liệu, chỉnh sửa trang nhanh (xoay, cắt, xóa viền đen) và tách/ghép hồ sơ PDF quy mô lớn.

---

## 📁 Cấu Trúc Thư Mục Nghiêm Ngặt

Để phần mềm có thể nhận diện và hoạt động chính xác, cấu trúc thư mục chứa tài liệu **INPUT** bắt buộc phải tuân thủ chuẩn 3 cấp như sau:

```text
<<Thư mục INPUT>>/
├── <<Hộp số 01>>/
│   ├── <<Hồ sơ A>>/
│   │   ├── tài_liệu_01.pdf
│   │   └── tài_liệu_02.pdf
│   └── <<Hồ sơ B>>/
│       └── tài_liệu_01.pdf
└── <<Hộp số 02>>/
    └── <<Hồ sơ C>>/
        ├── văn_bản_gốc.pdf
        └── tài_liệu_kèm_theo.pdf
```

> [!WARNING]
> **Lưu ý quan trọng**:
> - Phần mềm quét thư mục theo 3 tầng cấp: **`Thư mục INPUT` ➔ `Tên Hộp` ➔ `Tên Hồ sơ` ➔ `Các file PDF bên trong`**.
> - Không chứa các tệp tin PDF trực tiếp ngoài thư mục `Hộp` hoặc `Hồ sơ`.
> - Các thư mục Hồ sơ đã làm xong và có file kết quả trong thư mục **OUTPUT** tương ứng sẽ được tự động đánh dấu tích xanh (✅) trên cây thư mục.

---

## ⚡ Các Tính Năng Vượt Trội

### 1. Quản Lý Thư Mục & Trạng Thái Làm Việc
- **Quản lý Cây Thư Mục Trực Quan**: Sidebar bên trái hiển thị cấu trúc Hộp và Hồ sơ của thư mục INPUT đã chọn. Tự động lọc ẩn các tệp tin để tránh rối mắt.
- **Không Lưu Lịch Sử Đường Dẫn**: Mỗi lần mở ứng dụng, người dùng sẽ chọn lại thư mục làm việc từ đầu để đảm bảo bảo mật và tránh nhầm lẫn giữa các đợt tài liệu.
- **Ẩn/Hiện Sidebar**: Cho phép thu gọn Sidebar danh sách hồ sơ bằng nút bấm tiện lợi để dành toàn bộ không gian cho lưới ảnh trang PDF.

### 2. Tải & Hiển Thị Trang PDF Tốc Độ Cao (Không Trễ/Lag)
- **Tải Ảnh Lưới Siêu Tốc (Decoupled Grid Rendering)**: 
  - Ảnh hiển thị trên lưới được render ở độ phân giải tối ưu **72 DPI** và được thu nhỏ trước về kích thước **300px** trực tiếp trên luồng chạy ngầm.
  - Loại bỏ hoàn toàn hiện tượng nghẽn luồng giao diện chính (GUI Thread), cho phép cuộn lưới trang mượt mà ngay cả với hồ sơ hàng trăm trang.
- **Bộ Đệm RAM Cache Khủng 2 GB (Pre-caching)**:
  - Tự động chạy tiến trình ngầm quét và render trước các hồ sơ chưa làm trong danh sách vào RAM.
  - Khi nhấp chọn hồ sơ đã được pre-cache, toàn bộ các trang sẽ **hiển thị ngay lập tức (0 giây delay)**.
  - Thuật toán giải phóng bộ nhớ thông minh (LRU Eviction): Tự động giải phóng các hồ sơ cũ nhất khi cache đạt ngưỡng giới hạn **2 GB**.
  - Tự động xóa khỏi bộ nhớ đệm ngay khi hồ sơ được ngắt và xuất file thành công để giải phóng RAM cho các hồ sơ tiếp theo.

### 3. Công Cụ Chỉnh Sửa Trang PDF Trực Quan (Per-Page Controls)
- **Cắt Trang (Crop) ⛶**: Chọn vùng cắt tùy ý bằng cách kéo chuột trực quan. Phần mềm tự động tính toán tọa độ gốc để crop chính xác.
- **Xoay Góc Tự Do 📐 (Custom Angle Rotation)**: Hỗ trợ kéo trục lollipop để xoay trang ở bất kỳ góc độ nào (theo độ từ -180° đến 180°). Tự động tính toán mở rộng khung hình để không bị mất góc ảnh.
- **Tự Động Xóa Viền Đen 🧹 (Auto Clean Borders)**: Nhận diện và sơn trắng tự động các đường viền đen bị lỗi do quá trình quét (scan) tài liệu gây ra.
- **Xoay Trang Nhanh**: Xoay trái 90° (↺), xoay phải 90° (↻), hoặc xoay 180° (180).
- **Xóa Trang 🗑️**: Loại bỏ nhanh các trang thừa, trang trắng lỗi.
- **Kéo Thả Đổi Thứ Tự (Drag & Drop)**: Kéo thả trực tiếp các trang trên lưới để sắp xếp lại thứ tự xuất bản.
- **Đặt Điểm Ngắt (Breakpoint) ✂️**: Click chuột vào ảnh trang để thiết lập điểm cắt. Trang được đánh dấu sẽ trở thành trang đầu tiên của file PDF mới.

### 4. Tách & Ghép PDF Chất Lượng Gốc (Native Quality)
- **Chất Lượng Gốc 100%**: Các thao tác chỉnh sửa (xoay, cắt, sắp xếp) được ghi nhận dưới dạng ma trận biến đổi. Khi xuất file, ứng dụng thao tác trực tiếp trên các đối tượng Vector/Text của tài liệu PDF gốc. Kết quả xuất ra **giữ nguyên 100% độ sắc nét gốc** của tệp tin, không bị giảm chất lượng như các công cụ chuyển đổi sang ảnh khác.
- **Đặt Tên Tự Động**: Các file kết quả được lưu dưới dạng `01.pdf`, `02.pdf`... nằm trong thư mục đích tương ứng: `<<OUTPUT>>/<<Tên Hộp>>/<<Tên Hồ sơ>>/`.
- **Cảnh Báo Ghi Đè**: Nếu thư mục đầu ra đã chứa sẵn tệp tin, ứng dụng sẽ hiển thị thông báo yêu cầu người dùng xác nhận trước khi xóa/ghi đè.

---

## 🛠️ Yêu Cầu Cài Đặt

* **Hệ điều hành**: Windows 10/11, macOS, hoặc Linux.
* **Môi trường**: Python từ version **3.8** đến **3.11** (Khuyến nghị sử dụng Python 3.10).

---

## 🚀 Hướng Dẫn Cài Đặt & Khởi Chạy

### Bước 1: Cài đặt các thư viện phụ thuộc
Mở PowerShell/Terminal tại thư mục dự án và thực hiện cài đặt các thư viện trong file `requirements.txt`:
```powershell
pip install -r requirements.txt
```
*(File này bao gồm các thư viện cốt lõi: `PySide6` và `PyMuPDF`)*.

### Bước 2: Tạo dữ liệu mẫu để thử nghiệm nhanh (Tùy chọn)
Nếu bạn chưa có sẵn bộ hồ sơ kiểm thử tuân thủ cấu trúc thư mục nghiêm ngặt, hãy chạy script tạo thư mục mẫu tự động:
```powershell
python create_test_data.py
```
Script này sẽ tạo ra thư mục `test_input` chứa cấu trúc Hộp và các Hồ sơ mẫu với các tệp tin PDF ngẫu nhiên từ 2-5 trang.

### Bước 3: Khởi chạy ứng dụng
Chạy tệp tin chính để mở giao diện đồ họa:
```powershell
python main.py
```

---

## 📖 Hướng Dẫn Sử Dụng Chi Tiết

1. **Cấu hình đường dẫn thư mục**:
   - Nhấn **Chọn thư mục INPUT** ➔ Chọn thư mục gốc chứa các Hộp hồ sơ của bạn.
   - Nhấn **Chọn thư mục OUTPUT** ➔ Chọn thư mục bạn muốn lưu trữ kết quả sau khi tách.
2. **Chọn Hồ sơ làm việc**:
   - Duyệt cây danh mục bên trái, click đúp hoặc click chọn Hồ sơ cần làm.
   - Danh sách trang sẽ lập tức hiển thị lên màn hình (Lưới).
3. **Thay đổi DPI hiển thị (Khi cần)**:
   - Trên thanh Top Bar, bạn có thể lựa chọn mức DPI từ `100 DPI` (mặc định - siêu nhanh) đến `300 DPI` (cực nét).
   - *Lưu ý*: Mức DPI này chỉ áp dụng khi xem ảnh lớn trong hộp thoại Crop / Rotate. Lưới thumbnail hiển thị chính vẫn được tối ưu ở 72 DPI để đảm bảo tốc độ cuộn mượt mà nhất.
4. **Biên tập trang**:
   - Kéo thả các trang để thay đổi thứ tự.
   - Nhấn các nút chức năng dưới mỗi trang để Xoay nhanh, Xóa, Cắt vùng, Xoay góc tự do hoặc Xóa viền đen.
5. **Đánh dấu điểm ngắt (Tách file)**:
   - Nhấp chuột trái vào giữa ảnh trang PDF trên lưới. Trang sẽ xuất hiện viền đỏ nổi bật và biểu tượng cây kéo ✂️ báo hiệu trang này sẽ bắt đầu một file PDF mới.
6. **Xuất kết quả**:
   - Kiểm tra kỹ thứ tự và các điểm ngắt kéo trên màn hình.
   - Nhấn nút **Ngắt File** ở góc trên bên phải. Hệ thống sẽ thực hiện tách và thông báo khi thành công. Hồ sơ tương ứng trên cây thư mục sẽ xuất hiện dấu tích xanh ✅.
