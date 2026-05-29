# Kế hoạch triển khai: Ứng dụng Desktop xử lý và tách file PDF (Đã thống nhất)

Cảm ơn bạn đã bổ sung. Dưới đây là phương án kỹ thuật chi tiết đã thống nhất để triển khai ứng dụng.

---

## Các lựa chọn đã thống nhất

1. **Thư viện Giao diện (GUI)**: **PySide6** (Qt6 cho Python).
2. **Thư viện xử lý PDF**: **PyMuPDF (fitz)**.
3. **Cách hiển thị Điểm ngắt (Breakpoint)**: **Phương án A** (Nhấp 1 lần vào ảnh để đặt điểm ngắt, hiển thị đường viền màu đỏ nổi bật bao quanh trang ảnh được chọn kèm biểu tượng cây kéo ở góc; nhấp lần nữa để bỏ chọn).
4. **Hành vi sau khi ngắt file**: **Giữ nguyên giao diện** hiện tại (cho phép kiểm tra lại hoặc thực hiện tiếp các thao tác nếu cần).
5. **Xử lý Xoay/Xóa**: Thực hiện trên bộ nhớ/cache tạm thời, **không làm thay đổi file gốc ở thư mục `input`**. Chỉ render và lưu kết quả cuối cùng ra thư mục `output`.
6. **Đóng gói ứng dụng**: Chạy trực tiếp từ mã nguồn Python.
7. **[Bổ sung] Kiểm tra trùng lặp thư mục Output**:
   * Khi người dùng nhấn nút "Ngắt file", ứng dụng sẽ kiểm tra xem thư mục `output/<<hộp>>/<<hồ sơ>>/` đã tồn tại và có chứa file nào hay chưa.
   * Nếu có, hiển thị một **hộp thoại thông báo (QMessageBox)** cảnh báo: *"Thư mục đầu ra đã chứa các file PDF cũ. Bạn có muốn xóa sạch thư mục này và ghi lại mới từ đầu không?"* với hai lựa chọn **Có (Yes)** và **Không (No)**.
   * Nếu người dùng chọn Yes, hệ thống sẽ xóa toàn bộ nội dung trong thư mục đó và thực hiện lưu các file PDF mới. Nếu chọn No, quá trình ngắt file sẽ được hủy bỏ.

---

## Chi tiết kỹ thuật & Kiến trúc mã nguồn

### 1. Cấu trúc thư mục ứng dụng dự kiến
Chúng ta sẽ viết ứng dụng trong một file chính hoặc cấu trúc module đơn giản:
```
super_edit_pdf/
│
├── main.py              # File chạy chính của ứng dụng
├── requirements.txt     # Danh sách thư viện cần thiết (PySide6, PyMuPDF)
└── README.md            # Hướng dẫn chạy chương trình
```

### 2. Các lớp xử lý chính (Core Classes)
* **`PDFProcessor`**: Quản lý việc đọc các trang từ các file PDF trong một thư mục hồ sơ, lưu trữ thứ tự trang hiện tại, góc xoay của từng trang, trạng thái bị xóa của trang, và các điểm ngắt.
  * *Thuộc tính của mỗi trang*: `{"source_pdf": str, "page_index": int, "rotation": int, "is_deleted": bool, "has_breakpoint": bool}`.
  * *Hành vi*:
    * Đọc danh sách file PDF (được sắp xếp theo tên tăng dần).
    * Kết xuất hình ảnh (QImage/QPixmap) của từng trang để hiển thị lên UI.
    * Ghi file PDF đầu ra dựa trên danh sách trang hiện tại và các điểm ngắt.
* **`PageWidget`**: Hiển thị hình ảnh một trang PDF.
  * Hiển thị số thứ tự trang hiện tại dưới ảnh.
  * Hiển thị các nút: Xoay trái, Xoay phải, Xoay 180°, Xóa trang.
  * Nhấn vào ảnh để kích hoạt/hủy kích hoạt breakpoint (đổi viền đỏ và hiển thị/ẩn icon kéo).
  * Hỗ trợ Drag and Drop để di chuyển vị trí.
* **`PDFSplitterApp`**: Cửa sổ chính (MainWindow) chứa bố cục toàn màn hình.
  * **Sidebar**: Hiển thị cây thư mục (Hộp -> Hồ sơ) sử dụng `QTreeView` với bộ lọc chỉ hiển thị thư mục, ẩn các tệp tin.
  * **Top bar**: Chọn thư mục Input/Output, hiển thị tên Hồ sơ hiện tại.
  * **Main View**: Lưới ảnh (Grid View) hiển thị các `PageWidget` bên trong một scroll area. Có thanh điều khiển lưới (chọn kích thước lưới 1x1, 2x2, 2x1, 4x1...).

### 3. Logic tách file (Split Logic)
Giả sử ta có danh sách trang sau khi người dùng sắp xếp/xoay/xóa:
`P1, P2, P3*, P4, P5*, P6` (Dấu `*` đại diện cho điểm ngắt breakpoint đặt tại trang đó).
* File PDF 1 sẽ gồm: `P1, P2, P3` -> xuất ra `01.pdf`.
* File PDF 2 sẽ gồm: `P4, P5` -> xuất ra `02.pdf`.
* File PDF 3 sẽ gồm: `P6` -> xuất ra `03.pdf`.
* Đường dẫn xuất ra sẽ tự động tạo: `output/<<hộp>>/<<hồ sơ>>/01.pdf`, `output/<<hộp>>/<<hồ sơ>>/02.pdf`, v.v.

---

## Kế hoạch Kiểm thử (Verification Plan)

### Kiểm thử thủ công:
1. Chạy ứng dụng từ mã nguồn Python.
2. Chọn thư mục Input mẫu có cấu trúc `Hop_01/Ho_so_01/1.pdf`, `2.pdf` và thư mục Output.
3. Kiểm tra xem cây thư mục hiển thị đúng chỉ các Hộp và Hồ sơ, và Sidebar có thu gọn được không.
4. Chọn hồ sơ và kiểm tra việc hiển thị lưới các trang theo thứ tự file tăng dần.
5. Thử nghiệm đổi kích thước lưới (1x1, 2x2...).
6. Thực hiện kéo thả thay đổi thứ tự trang, kiểm tra số thứ tự cập nhật.
7. Xoay trang (trái/phải/180°) và kiểm tra hình ảnh xoay tương ứng trên lưới.
8. Xóa một vài trang.
9. Đặt điểm ngắt (click vào ảnh -> viền đỏ xuất hiện).
10. Nhấp nút "Ngắt file" lần đầu và xác minh các file PDF con được tạo ra trong thư mục Output với đúng cấu trúc.
11. Nhấp nút "Ngắt file" lần thứ hai (thư mục output lúc này đã có file). Kiểm tra xem có hiển thị hộp thoại hỏi ý kiến hay không:
    * Nếu chọn **Không**: Quá trình ngắt bị hủy bỏ, các file trong output giữ nguyên.
    * Nếu chọn **Có**: Thư mục output tương ứng bị xóa hết file cũ và ghi đè các file mới thành công.
12. Xác nhận giao diện vẫn giữ nguyên sau thao tác.
