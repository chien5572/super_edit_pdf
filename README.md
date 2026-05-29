# Bộ Xử Lý & Tách File PDF (PDF Splitter)

Ứng dụng Desktop chuyên nghiệp viết bằng Python, sử dụng giao diện hiện đại **PySide6** và nhân xử lý PDF tốc độ cao **PyMuPDF (fitz)**.

## Tính năng chính

1. **Quản lý cấu trúc thư mục đầu vào & đầu ra**:
   * Quét và hiển thị cấu trúc `input/<<hộp>>/<<hồ sơ>>` dưới dạng cây thư mục trực quan ở sidebar bên trái.
   * Cho phép thu gọn/mở rộng cây thư mục và ẩn/hiện toàn bộ sidebar để tối ưu không gian làm việc.
   * Tự động nhớ đường dẫn đã chọn lần trước cho lần mở ứng dụng tiếp theo.
2. **Hiển thị hình ảnh trang PDF chất lượng cao**:
   * Tải và render các trang PDF bất đồng bộ (multi-threading) không gây đơ/treo giao diện.
   * Hiển thị lưới hình ảnh với các chế độ thu phóng linh hoạt: `1x1`, `2x1`, `2x2`, `3x3`, `4x1`, `5x5`.
3. **Thao tác tương tác trang trực quan**:
   * **Kéo thả (Drag & Drop)** trực tiếp trên lưới để thay đổi thứ tự trang nhanh chóng.
   * **Xoay trang** linh hoạt (Xoay trái 90°, Xoay phải 90°, Xoay 180°).
   * **Xóa trang** không mong muốn.
   * **Đặt điểm ngắt (Breakpoint)**: Nhấn trực tiếp lên ảnh để đánh dấu điểm ngắt (đổi viền đỏ và hiển thị biểu tượng cây kéo ✂️). Click lại để hủy.
4. **Ngắt và Xuất file PDF**:
   * Nhấn nút **Ngắt file** để tự động ghép các trang tương ứng thành các file PDF mới theo thứ tự `01.pdf`, `02.pdf`...
   * Tự động tạo cấu trúc thư mục đích dạng `output/<<hộp>>/<<hồ sơ>>`.
   * **Hỏi xác nhận ghi đè**: Nếu thư mục đầu ra đã có sẵn dữ liệu cũ, ứng dụng sẽ hiện cảnh báo hỏi ý kiến người dùng có muốn xóa sạch để ghi lại mới hay không.
   * Đảm bảo an toàn 100%: Mọi thao tác xoay, xóa, sắp xếp chỉ diễn ra trên bộ nhớ tạm thời của ứng dụng, **không chỉnh sửa hay làm thay đổi file PDF gốc**.

## Yêu cầu hệ thống

* Python 3.8 trở lên.
* Các thư viện cần thiết: `PySide6`, `pymupdf`.

## Hướng dẫn cài đặt và chạy ứng dụng

1. **Cài đặt thư viện**:
   Mở terminal (PowerShell hoặc Command Prompt) tại thư mục dự án và chạy lệnh:
   ```bash
   pip install -r requirements.txt
   ```

2. **Tạo dữ liệu kiểm thử (Nếu muốn thử nghiệm nhanh)**:
   Chạy script tạo thư mục và file PDF mẫu:
   ```bash
   python create_test_data.py
   ```
   Lệnh này sẽ tạo thư mục `test_input` với một số Hộp và Hồ sơ chứa file PDF mẫu 2-5 trang để kiểm thử.

3. **Chạy ứng dụng**:
   Khởi động giao diện chính của ứng dụng bằng lệnh:
   ```bash
   python main.py
   ```
