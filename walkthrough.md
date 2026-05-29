# Walkthrough: Tự động xóa viền đen (Tô trắng) trang PDF

Tính năng tự động phát hiện và xóa viền đen đã được triển khai hoàn tất vào ứng dụng. Dưới đây là các thay đổi và kết quả thử nghiệm.

## Các thay đổi chính trong mã nguồn

### 1. Thuật toán phát hiện viền đen siêu tốc
* Thêm hàm `detect_black_borders(qimage)` vào [main.py](file:///d:/workspace/vibe-code-app/super_edit_pdf/super_edit_pdf/main.py):
  * Tự động scale ảnh về kích thước nhỏ `150x200` để quét nhanh và mượt mà (< 10ms).
  * Quét từ 4 cạnh đi vào trong để tìm vùng có mật độ pixel tối (> 15% diện tích cạnh quét).
  * Giới hạn vùng quét tối đa 20% kích thước ảnh để đảm bảo không lấn vào vùng nội dung văn bản.
  * Trả về tỷ lệ viền dạng thập phân `(left_ratio, top_ratio, right_ratio, bottom_ratio)`.

### 2. Cập nhật giao diện `PageWidget`
* Bổ sung nút bấm 🧹 (Tự động xóa viền đen) vào hàng công cụ bên dưới mỗi trang.
* Cập nhật `PageWidget.update_state()` để đổi màu nền nút 🧹 sang màu xanh lục nổi bật khi tính năng xóa viền được kích hoạt.
* Cập nhật `PageWidget.update_display()` để vẽ đè 4 dải hình chữ nhật màu trắng tương ứng lên ảnh thumbnail của trang dựa trên kết quả phát hiện viền.

### 3. Cập nhật logic xuất file `PDFProcessor.split_pdf`
* Khi xuất các file PDF con, nếu trang tài liệu có cấu hình xóa viền, hệ thống sẽ tự động vẽ đè 4 hình chữ nhật vector màu trắng lên 4 cạnh trang tương ứng sử dụng `page.draw_rect()` trong PyMuPDF.
* Điều này giúp loại bỏ viền đen hoàn toàn ở file PDF xuất ra mà không ảnh hưởng tới dung lượng file hoặc độ sắc nét của văn bản scan.

### 4. Tự động cuộn trang lên đầu khi chuyển đổi hồ sơ
* Cập nhật phương thức `PDFSplitterApp.load_ho_so_pages()` để tự động đặt lại giá trị của các thanh cuộn dọc (vertical scrollbar) và cuộn ngang (horizontal scrollbar) về `0`.
* Việc này đảm bảo khi người dùng click chọn hồ sơ mới, màn hình làm việc sẽ được đưa về vị trí đầu trang thay vì giữ nguyên vị trí cuộn của hồ sơ cũ trước đó.

### 5. Đánh dấu hồ sơ đã hoàn thành (Dấu check xanh ✅)
* Thêm phương thức `PDFSplitterApp.update_tree_checkmarks()` để tự động kiểm tra xem các thư mục hồ sơ tương ứng ở thư mục `output` đã tồn tại và chứa file PDF con hay chưa.
* Nếu đã tồn tại kết quả đầu ra, tự động thêm biểu tượng ✅ vào bên phải tên hồ sơ trên cây thư mục.
* Các liên kết tự động gọi làm tươi checkmarks:
  * Khi chọn thư mục Input ban đầu.
  * Khi thay đổi hoặc chọn lại thư mục Output.
  * Khi thực hiện tác vụ **Ngắt File** thành công (checkmark xuất hiện ngay lập tức trên hồ sơ đang làm việc).

---

## Cách kiểm thử trực quan

1. **Khởi chạy ứng dụng**:
   Chạy lệnh sau tại thư mục dự án:
   ```bash
   python main.py
   ```
2. **Chọn Hồ sơ có trang tài liệu bị viền đen**.
3. **Kích hoạt tính năng**:
   * Click vào biểu tượng chổi quét 🧹 dưới chân trang.
   * Viền đen sẽ ngay lập tức được phủ trắng trên giao diện. Nút 🧹 chuyển sang màu xanh lá.
   * Để hoàn tác, click lại nút 🧹 một lần nữa.
4. **Xuất PDF**:
   * Nhấn nút **Ngắt File** để xuất các file PDF con vào thư mục `output`.
   * Mở file PDF đầu ra và kiểm tra các viền đen đã được loại bỏ sạch sẽ.

## Đẩy mã nguồn lên GitHub
* Toàn bộ các thay đổi trên đã được commit và push thành công lên GitHub tại: `https://github.com/chien5572/super_edit_pdf` (Nhánh `main`).
