import os
import sys
import re
import shutil
import fitz  # PyMuPDF
from PySide6.QtCore import Qt, QPoint, QMimeData, Signal, QThread, QSettings, QSize, QRect, QPointF
from PySide6.QtGui import QPixmap, QImage, QStandardItemModel, QStandardItem, QDrag, QTransform, QIcon, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTreeView, QScrollArea, QGridLayout,
    QLabel, QComboBox, QSplitter, QMessageBox, QFrame, QSizePolicy,
    QLineEdit, QDialog, QRubberBand, QSlider, QDoubleSpinBox
)

# Helper function for natural sorting (e.g., 1.pdf, 2.pdf, 10.pdf)
def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

# Automatic black border detection
def detect_black_borders(qimage):
    # Scale down to speed up pixel analysis (about 100x130 or 150x200 is fast)
    analyze_w = 150
    analyze_h = 200
    scaled = qimage.scaled(analyze_w, analyze_h, Qt.IgnoreAspectRatio, Qt.FastTransformation)
    
    W = scaled.width()
    H = scaled.height()
    
    # Threshold for dark pixels
    def is_dark(color):
        return color.red() < 65 and color.green() < 65 and color.blue() < 65

    # Max scan limits (20% of dimension to avoid text cropping)
    max_scan_w = W // 5
    max_scan_h = H // 5
    
    left = 0
    for x in range(max_scan_w):
        dark_count = 0
        for y in range(H):
            if is_dark(scaled.pixelColor(x, y)):
                dark_count += 1
        if dark_count / H >= 0.15:
            left = x + 1
        else:
            break
            
    right = 0
    for x in range(max_scan_w):
        col = W - 1 - x
        dark_count = 0
        for y in range(H):
            if is_dark(scaled.pixelColor(col, y)):
                dark_count += 1
        if dark_count / H >= 0.15:
            right = x + 1
        else:
            break
            
    top = 0
    for y in range(max_scan_h):
        dark_count = 0
        for x in range(W):
            if is_dark(scaled.pixelColor(x, y)):
                dark_count += 1
        if dark_count / W >= 0.15:
            top = y + 1
        else:
            break
            
    bottom = 0
    for y in range(max_scan_h):
        row = H - 1 - y
        dark_count = 0
        for x in range(W):
            if is_dark(scaled.pixelColor(x, row)):
                dark_count += 1
        if dark_count / W >= 0.15:
            bottom = y + 1
        else:
            break
            
    # Return border ratios (between 0.0 and 1.0)
    return (left / W, top / H, right / W, bottom / H)

# Background worker to load and render PDF pages to QImage (thread-safe)
class PageLoadWorker(QThread):
    page_loaded = Signal(int, QImage, dict)  # (global_page_idx, qimage, page_info)
    finished = Signal()
    progress_status = Signal(str)

    def __init__(self, ho_so_path):
        super().__init__()
        self.ho_so_path = ho_so_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            # List all pdf files and sort them naturally
            files = sorted(
                [f for f in os.listdir(self.ho_so_path) if f.lower().endswith('.pdf')],
                key=natural_sort_key
            )
        except Exception as e:
            self.progress_status.emit(f"Lỗi đọc thư mục: {str(e)}")
            self.finished.emit()
            return

        if not files:
            self.progress_status.emit("Thư mục trống hoặc không chứa file PDF.")
            self.finished.emit()
            return

        global_page_idx = 0
        total_files = len(files)

        for file_idx, file in enumerate(files):
            if self._is_cancelled:
                break

            pdf_path = os.path.join(self.ho_so_path, file)
            self.progress_status.emit(f"Đang đọc file ({file_idx + 1}/{total_files}): {file}...")

            try:
                doc = fitz.open(pdf_path)
                num_pages = len(doc)
                for page_idx in range(num_pages):
                    if self._is_cancelled:
                        break

                    page = doc[page_idx]
                    # Render page at 150 DPI for high quality layout view
                    zoom = 150 / 72
                    mat = fitz.Matrix(zoom, zoom)
                    pix = page.get_pixmap(matrix=mat, alpha=False)

                    # Create QImage from raw bytes. Copy is necessary because
                    # fitz Pixmap buffer will be reclaimed upon loop iteration/close.
                    qimg = QImage(
                        pix.samples,
                        pix.width,
                        pix.height,
                        pix.stride,
                        QImage.Format_RGB888
                    ).copy()

                    page_info = {
                        "source_pdf": pdf_path,
                        "original_page_index": page_idx,
                        "rotation": 0,  # Relative rotation (0, 90, 180, 270)
                        "custom_angle": 0.0,
                        "is_deleted": False,
                        "has_breakpoint": False
                    }

                    self.page_loaded.emit(global_page_idx, qimg, page_info)
                    global_page_idx += 1

                doc.close()
            except Exception as e:
                print(f"Error loading PDF {pdf_path}: {e}")

        self.finished.emit()


# Individual widget representing a single PDF page
class PageWidget(QFrame):
    clicked = Signal(int)                   # Emits the index of this page
    rotate_requested = Signal(int, int)    # Emits (page_id, rotation_delta)
    delete_requested = Signal(int)          # Emits page_id
    crop_requested = Signal(int)            # Emits page_id
    rotate_angle_requested = Signal(int)    # Emits page_id
    clean_borders_requested = Signal(int)    # Emits page_id

    def __init__(self, page_info, target_width=200, parent=None):
        super().__init__(parent)
        self.page_info = page_info
        self.page_id = page_info["id"]
        self.index = 0  # Position in the active grid list (updated dynamically)
        self.target_width = target_width
        self.drag_start_position = QPoint()

        self.init_ui()
        self.update_state()

    def init_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("PageWidget")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Page Thumbnail image
        self.lbl_image = QLabel(self)
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.lbl_image)

        # 2. Controls Panel under the image (divided into 2 rows for responsive fitting)
        bottom_layout = QVBoxLayout()
        bottom_layout.setSpacing(4)
        bottom_layout.setContentsMargins(2, 0, 2, 0)

        # Row 1: Index label and Delete button
        row1_layout = QHBoxLayout()
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(4)

        self.lbl_index = QLabel(self)
        self.lbl_index.setObjectName("lblIndex")
        self.lbl_index.setStyleSheet("font-weight: bold; font-size: 11px;")
        row1_layout.addWidget(self.lbl_index)
        
        row1_layout.addStretch()

        self.btn_delete = QPushButton("🗑️", self)
        self.btn_delete.setToolTip("Xóa trang")
        self.btn_delete.setFixedSize(22, 18)
        self.btn_delete.setObjectName("btnDelete")
        self.btn_delete.clicked.connect(lambda: self.delete_requested.emit(self.page_id))
        row1_layout.addWidget(self.btn_delete)

        bottom_layout.addLayout(row1_layout)

        # Row 2: Adjustment tools (↺, ↻, 180, ⛶, 📐)
        row2_layout = QHBoxLayout()
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(4)
        row2_layout.setAlignment(Qt.AlignCenter)

        # Rotation Buttons
        self.btn_rot_left = QPushButton("↺", self)
        self.btn_rot_left.setToolTip("Xoay trái 90°")
        self.btn_rot_left.setFixedSize(22, 18)
        self.btn_rot_left.setObjectName("btnControl")
        self.btn_rot_left.clicked.connect(lambda: self.rotate_requested.emit(self.page_id, -90))
        row2_layout.addWidget(self.btn_rot_left)

        self.btn_rot_right = QPushButton("↻", self)
        self.btn_rot_right.setToolTip("Xoay phải 90°")
        self.btn_rot_right.setFixedSize(22, 18)
        self.btn_rot_right.setObjectName("btnControl")
        self.btn_rot_right.clicked.connect(lambda: self.rotate_requested.emit(self.page_id, 90))
        row2_layout.addWidget(self.btn_rot_right)

        self.btn_rot_180 = QPushButton("180", self)
        self.btn_rot_180.setToolTip("Xoay 180°")
        self.btn_rot_180.setFixedSize(26, 18)
        self.btn_rot_180.setObjectName("btnControl")
        self.btn_rot_180.clicked.connect(lambda: self.rotate_requested.emit(self.page_id, 180))
        row2_layout.addWidget(self.btn_rot_180)

        # Crop Button
        self.btn_crop = QPushButton("⛶", self)
        self.btn_crop.setToolTip("Cắt trang (Crop)")
        self.btn_crop.setFixedSize(22, 18)
        self.btn_crop.setObjectName("btnControl")
        self.btn_crop.clicked.connect(lambda: self.crop_requested.emit(self.page_id))
        row2_layout.addWidget(self.btn_crop)

        # Rotate Custom Angle Button
        self.btn_rotate_angle = QPushButton("📐", self)
        self.btn_rotate_angle.setToolTip("Xoay góc tự do")
        self.btn_rotate_angle.setFixedSize(22, 18)
        self.btn_rotate_angle.setObjectName("btnControl")
        self.btn_rotate_angle.clicked.connect(lambda: self.rotate_angle_requested.emit(self.page_id))
        row2_layout.addWidget(self.btn_rotate_angle)

        # Clean Borders Button
        self.btn_clean_borders = QPushButton("🧹", self)
        self.btn_clean_borders.setToolTip("Tự động xóa viền đen")
        self.btn_clean_borders.setFixedSize(22, 18)
        self.btn_clean_borders.setObjectName("btnControl")
        self.btn_clean_borders.clicked.connect(lambda: self.clean_borders_requested.emit(self.page_id))
        row2_layout.addWidget(self.btn_clean_borders)

        bottom_layout.addLayout(row2_layout)

        layout.addLayout(bottom_layout)

    def update_display(self):
        # Update text info
        scissor_tag = "  ✂️ [CẮT]" if self.page_info["has_breakpoint"] else ""
        self.lbl_index.setText(f"Trang {self.index + 1}{scissor_tag}")

        # Rotate the cached QPixmap for display
        original_pixmap = self.page_info["pixmap"]
        
        # If white_borders is enabled, paint white rectangles on a copy of the original pixmap
        white_borders = self.page_info.get("white_borders")
        if white_borders:
            temp_pixmap = original_pixmap.copy()
            painter = QPainter(temp_pixmap)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255))
            
            w = temp_pixmap.width()
            h = temp_pixmap.height()
            left_r, top_r, right_r, bottom_r = white_borders
            
            if left_r > 0:
                painter.drawRect(0, 0, int(left_r * w), h)
            if right_r > 0:
                painter.drawRect(w - int(right_r * w), 0, int(right_r * w), h)
            if top_r > 0:
                painter.drawRect(0, 0, w, int(top_r * h))
            if bottom_r > 0:
                painter.drawRect(0, h - int(bottom_r * h), w, int(bottom_r * h))
            painter.end()
            disp_pixmap = temp_pixmap
        else:
            disp_pixmap = original_pixmap

        rotation_angle = self.page_info.get("rotation", 0)
        custom_angle = self.page_info.get("custom_angle", 0.0)
        total_angle = rotation_angle + custom_angle

        if total_angle != 0.0:
            transform = QTransform().rotate(total_angle)
            disp_pixmap = disp_pixmap.transformed(transform, Qt.SmoothTransformation)

        # Scaled smoothly to the current target width matching grid mode selection
        scaled_pixmap = disp_pixmap.scaledToWidth(self.target_width, Qt.SmoothTransformation)
        self.lbl_image.setPixmap(scaled_pixmap)

    def update_state(self):
        # Find the main window to check the current theme
        main_win = self.window()
        theme = getattr(main_win, "current_theme", "light")
        has_bp = self.page_info["has_breakpoint"]
        has_wb = "white_borders" in self.page_info

        # Style difference for breakpoint active vs inactive based on active theme
        if theme == "dark":
            if has_bp:
                self.lbl_image.setStyleSheet("border: 3px solid #ff4d4d; border-radius: 4px; background-color: #000000;")
                self.setStyleSheet("QWidget#PageWidget { border: 2px solid #ff4d4d; background-color: #2b1d1f; border-radius: 6px; }")
            else:
                self.lbl_image.setStyleSheet("border: 1px solid #2d2d34; border-radius: 4px; background-color: #000000;")
                self.setStyleSheet("QWidget#PageWidget { border: 1px solid #2d2d34; background-color: #1a1a20; border-radius: 6px; }")
        else:  # light theme
            if has_bp:
                self.lbl_image.setStyleSheet("border: 3px solid #ff3b30; border-radius: 4px; background-color: #ffffff;")
                self.setStyleSheet("QWidget#PageWidget { border: 2px solid #ff3b30; background-color: #ffebe9; border-radius: 6px; }")
            else:
                self.lbl_image.setStyleSheet("border: 1px solid #d1d1d6; border-radius: 4px; background-color: #ffffff;")
                self.setStyleSheet("QWidget#PageWidget { border: 1px solid #d1d1d6; background-color: #ffffff; border-radius: 6px; }")

        if has_wb:
            self.btn_clean_borders.setStyleSheet("background-color: #34c759; color: white; border-color: #34c759;")
        else:
            self.btn_clean_borders.setStyleSheet("")

        self.update_display()

    # Drag-and-drop source implementation
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if (event.position().toPoint() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        # Pass the visible index as identifying text
        mime_data.setText(str(self.index))
        drag.setMimeData(mime_data)

        # Create drag preview image (slightly transparent)
        preview = self.grab().scaled(100, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        drag.setPixmap(preview)
        drag.setHotSpot(QPoint(preview.width() / 2, preview.height() / 2))

        drag.exec(Qt.MoveAction)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Check if it is a simple click (not dragging)
            if (event.position().toPoint() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
                self.clicked.emit(self.index)


# Scrollable grid container managing PageWidgets and custom Drop events
class PageGridWidget(QWidget):
    reordered = Signal(int, int)  # (src_index, dst_index)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setContentsMargins(15, 15, 15, 15)
        self.grid_layout.setSpacing(15)
        
        self.widgets = []
        self.columns = 3

    def set_columns(self, cols):
        self.columns = cols
        self.rearrange_grid()

    def clear_grid(self):
        for widget in self.widgets:
            widget.deleteLater()
        self.widgets.clear()
        
        # Clear layout contents
        for i in reversed(range(self.grid_layout.count())):
            self.grid_layout.takeAt(i)

    def rearrange_grid(self):
        # Temporarily extract widgets from layout
        for i in reversed(range(self.grid_layout.count())):
            self.grid_layout.takeAt(i)

        for idx, widget in enumerate(self.widgets):
            widget.index = idx
            widget.update_display()
            
            row = idx // self.columns
            col = idx % self.columns
            self.grid_layout.addWidget(widget, row, col)

    # Drag-and-drop target implementation
    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        try:
            src_idx = int(event.mimeData().text())
        except ValueError:
            return

        pos = event.position().toPoint()
        dst_child = self.childAt(pos)

        # Traverse up to locate parent PageWidget
        parent_widget = dst_child
        while parent_widget and not isinstance(parent_widget, PageWidget):
            parent_widget = parent_widget.parent()

        if parent_widget and parent_widget.index != src_idx:
            dst_idx = parent_widget.index
            self.reordered.emit(src_idx, dst_idx)
            event.acceptProposedAction()
        elif parent_widget is None or parent_widget == self:
            # Dropped in empty grid space: append to end
            dst_idx = len(self.widgets) - 1
            if dst_idx != src_idx and dst_idx >= 0:
                self.reordered.emit(src_idx, dst_idx)
                event.acceptProposedAction()


# Logic controller to manage active loaded PDF pages and splitting operation
class PDFProcessor:
    def __init__(self):
        self.pages = []  # List of page_info dicts representing the dossier state

    def clear(self):
        self.pages.clear()

    def reorder_pages(self, src_visible_idx, dst_visible_idx):
        # Convert visible index mapping to actual page index in the full list
        visible_indices = [idx for idx, p in enumerate(self.pages) if not p["is_deleted"]]
        if src_visible_idx >= len(visible_indices) or dst_visible_idx >= len(visible_indices):
            return
            
        actual_src = visible_indices[src_visible_idx]
        actual_dst = visible_indices[dst_visible_idx]
        
        # Pop and insert in the actual self.pages list
        page_to_move = self.pages.pop(actual_src)
        self.pages.insert(actual_dst, page_to_move)

    def split_pdf(self, output_dir, hop_name, ho_so_name):
        visible_pages = [p for p in self.pages if not p["is_deleted"]]
        if not visible_pages:
            return False, "Không có trang nào để xuất."

        # Group pages into segments based on breakpoints
        # A page with a breakpoint marks the START of a new segment (except the first page).
        segments = []
        current_segment = []

        for idx, p in enumerate(visible_pages):
            if p["has_breakpoint"] and idx > 0:
                if current_segment:
                    segments.append(current_segment)
                current_segment = [p]
            else:
                current_segment.append(p)

        if current_segment:
            segments.append(current_segment)

        # Create destination directory output/<<hộp>>/<<hồ sơ>>
        target_dir = os.path.join(output_dir, hop_name, ho_so_name)
        os.makedirs(target_dir, exist_ok=True)

        open_docs = {}
        try:
            for idx, segment in enumerate(segments):
                out_doc = fitz.open()
                for p_info in segment:
                    src_path = p_info["source_pdf"]
                    # Cache open document reference to avoid repeated disk reads
                    if src_path not in open_docs:
                        open_docs[src_path] = fitz.open(src_path)
                    src_doc = open_docs[src_path]

                    orig_idx = p_info["original_page_index"]
                    orig_page = src_doc[orig_idx]
                    
                    # Draw white borders on orig_page in memory if configured
                    wb = p_info.get("white_borders")
                    if wb:
                        left_r, top_r, right_r, bottom_r = wb
                        pdf_w = orig_page.rect.width
                        pdf_h = orig_page.rect.height
                        if left_r > 0:
                            orig_page.draw_rect(fitz.Rect(0, 0, left_r * pdf_w, pdf_h), color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
                        if right_r > 0:
                            orig_page.draw_rect(fitz.Rect(pdf_w - right_r * pdf_w, 0, pdf_w, pdf_h), color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
                        if top_r > 0:
                            orig_page.draw_rect(fitz.Rect(0, 0, pdf_w, top_r * pdf_h), color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
                        if bottom_r > 0:
                            orig_page.draw_rect(fitz.Rect(0, pdf_h - bottom_r * pdf_h, pdf_w, pdf_h), color=(1, 1, 1), fill=(1, 1, 1), overlay=True)

                    orig_rotation = orig_page.rotation
                    user_rotation = p_info.get("rotation", 0)
                    custom_angle = p_info.get("custom_angle", 0.0)

                    if custom_angle == 0.0:
                        # Insert the single page
                        out_doc.insert_pdf(src_doc, from_page=orig_idx, to_page=orig_idx)

                        # Calculate final rotation: (original PDF page rotation + user GUI rotation) % 360
                        final_rotation = (orig_rotation + user_rotation) % 360
                        
                        out_page = out_doc[-1]
                        out_page.set_rotation(final_rotation)

                        # Apply crop if present
                        c = p_info.get("crop_rect")
                        if c:
                            # Map crop box from rotated Original Page space back to unrotated space
                            matrix = ~orig_page.rotation_matrix
                            unrotated_rect = fitz.Rect(c[0], c[1], c[2], c[3]) * matrix
                            unrotated_rect.normalize()
                            out_page.set_cropbox(unrotated_rect)
                    else:
                        # Custom rotation path: create a new page and show the source page on it rotated
                        c = p_info.get("crop_rect")
                        if c:
                            clip_rect = fitz.Rect(c[0], c[1], c[2], c[3])
                        else:
                            clip_rect = orig_page.rect

                        import math
                        w = clip_rect.width
                        h = clip_rect.height
                        
                        total_extra_angle = user_rotation + custom_angle
                        
                        # Calculate the bounding box of the rotated clip_rect
                        theta = math.radians(total_extra_angle)
                        cos_t = abs(math.cos(theta))
                        sin_t = abs(math.sin(theta))
                        w_new = w * cos_t + h * sin_t
                        h_new = w * sin_t + h * cos_t
                        
                        # Create the new page in out_doc
                        out_page = out_doc.new_page(width=w_new, height=h_new)
                        dest_rect = out_page.rect
                        
                        if c:
                            matrix = ~orig_page.rotation_matrix
                            src_clip = fitz.Rect(c[0], c[1], c[2], c[3]) * matrix
                            src_clip.normalize()
                            
                            out_page.show_pdf_page(
                                dest_rect,
                                src_doc,
                                pno=orig_idx,
                                rotate=-total_extra_angle,
                                clip=src_clip,
                                keep_proportion=True
                            )
                        else:
                            out_page.show_pdf_page(
                                dest_rect,
                                src_doc,
                                pno=orig_idx,
                                rotate=-total_extra_angle,
                                keep_proportion=True
                            )

                # Output filename 01.pdf, 02.pdf, etc.
                out_name = f"{idx + 1:02d}.pdf"
                out_path = os.path.join(target_dir, out_name)
                
                # Write to disk with optimizations
                out_doc.save(out_path, garbage=3, deflate=True)
                out_doc.close()

            return True, f"Tách thành công thành {len(segments)} file PDF tại:\n{target_dir}"
        except Exception as e:
            return False, str(e)
        finally:
            # Clean up all cached open files
            for doc in open_docs.values():
                doc.close()


# Layout config mapping from Grid dropdown mode selection to (columns, page_width)
GRID_MODES = {
    "1x1": (1, 680),
    "2x1": (2, 380),
    "2x2": (2, 380),
    "3x3": (3, 250),
    "4x1": (4, 180),
    "5x5": (5, 140)
}


class CropLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rubber_band = None
        self.origin = QPoint()
        self.crop_rect = QRect()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.origin = event.position().toPoint()
            if not self.rubber_band:
                self.rubber_band = QRubberBand(QRubberBand.Rectangle, self)
            # Style rubberband for visual clarity
            self.rubber_band.setStyleSheet("border: 2px dashed #ff3b30; background-color: rgba(255, 59, 48, 0.15);")
            self.rubber_band.setGeometry(QRect(self.origin, QSize()))
            self.rubber_band.show()

    def mouseMoveEvent(self, event):
        if self.rubber_band:
            self.rubber_band.setGeometry(QRect(self.origin, event.position().toPoint()).normalized())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.rubber_band:
                self.crop_rect = QRect(self.origin, event.position().toPoint()).normalized()


class CropDialog(QDialog):
    def __init__(self, full_pixmap, pdf_w, pdf_h, parent=None):
        super().__init__(parent)
        self.full_pixmap = full_pixmap
        self.pdf_w = pdf_w
        self.pdf_h = pdf_h
        self.reset_requested = False

        self.setWindowTitle("Cắt ảnh (Crop Page)")
        
        # 1. Initialize UI first to build all widgets
        self.init_ui()

        # 2. Set window flags and show full screen
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.showFullScreen()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 1. Top Panel for Controls & Instructions
        top_panel = QFrame(self)
        top_panel.setObjectName("TopPanel")
        
        main_win = self.parent()
        is_dark = getattr(main_win, "current_theme", "light") == "dark"
        if is_dark:
            top_panel.setStyleSheet("background-color: #1a1a20; border: 1px solid #2d2d34; border-radius: 6px; min-height: 40px;")
        else:
            top_panel.setStyleSheet("background-color: #ffffff; border: 1px solid #d1d1d6; border-radius: 6px; min-height: 40px;")

        top_layout = QHBoxLayout(top_panel)
        top_layout.setContentsMargins(10, 4, 10, 4)

        lbl_instruct = QLabel("Kéo chuột chọn vùng để Cắt (Crop). Phím tắt: [Enter/OK] ghi nhận, [Esc/Hủy] để thoát.", self)
        lbl_instruct.setStyleSheet("font-weight: bold; font-size: 12px;" + ("color: #e2e2e6;" if is_dark else "color: #1c1c1e;"))
        top_layout.addWidget(lbl_instruct)
        top_layout.addStretch()

        # Reset button
        btn_reset = QPushButton("Xóa Cắt (Reset)", self)
        btn_reset.setFixedWidth(120)
        btn_reset.setStyleSheet("background-color: #f2f2f7; color: #1c1c1e;" if not is_dark else "background-color: #2a2a32; color: #e2e2e6;")
        btn_reset.clicked.connect(self.on_reset)
        top_layout.addWidget(btn_reset)

        # Cancel button
        btn_cancel = QPushButton("Hủy (Esc)", self)
        btn_cancel.setFixedWidth(90)
        btn_cancel.setStyleSheet("background-color: #f2f2f7; color: #1c1c1e;" if not is_dark else "background-color: #2a2a32; color: #e2e2e6;")
        btn_cancel.clicked.connect(self.reject)
        top_layout.addWidget(btn_cancel)

        # OK button
        btn_ok = QPushButton("OK (Enter)", self)
        btn_ok.setFixedWidth(95)
        if is_dark:
            btn_ok.setStyleSheet("background-color: #d9383a; color: white; font-weight: bold;")
        else:
            btn_ok.setStyleSheet("background-color: #ff3b30; color: white; font-weight: bold;")
        btn_ok.clicked.connect(self.accept)
        top_layout.addWidget(btn_ok)

        layout.addWidget(top_panel)

        # 2. Scroll area containing the centered image
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        if is_dark:
            self.scroll_area.setStyleSheet("background-color: #0c0c0e; border: 1px solid #2d2d34;")
        else:
            self.scroll_area.setStyleSheet("background-color: #e5e5ea; border: 1px solid #d1d1d6;")

        container = QWidget()
        container.setObjectName("ScrollContainer")
        container.setStyleSheet("background-color: transparent;")
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setAlignment(Qt.AlignCenter)

        self.crop_label = CropLabel(container)
        self.crop_label.setAlignment(Qt.AlignCenter)
        
        container_layout.addWidget(self.crop_label)
        self.scroll_area.setWidget(container)
        layout.addWidget(self.scroll_area)

    def showEvent(self, event):
        super().showEvent(event)
        # Perform image scaling after the dialog is shown and visible size is resolved
        self.scale_image_to_fit()

    def scale_image_to_fit(self):
        w = self.scroll_area.viewport().width()
        h = self.scroll_area.viewport().height()
        
        # Fallback if viewport sizes are not resolved yet
        if w < 100 or h < 100:
            screen = QApplication.primaryScreen().geometry()
            w = screen.width() - 80
            h = screen.height() - 150
            
        # Leave a 10px safety padding to guarantee no scrollbars are triggered
        max_w = w - 10
        max_h = h - 10
        
        self.scaled_pixmap = self.full_pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.crop_label.setPixmap(self.scaled_pixmap)
        self.crop_label.setFixedSize(self.scaled_pixmap.size())

    def on_reset(self):
        self.reset_requested = True
        self.accept()

    def get_mapped_crop_rect(self):
        if self.reset_requested:
            return None

        rect = self.crop_label.crop_rect
        if not rect or rect.width() <= 10 or rect.height() <= 10:
            return -1

        img_w = self.scaled_pixmap.width()
        img_h = self.scaled_pixmap.height()

        fx = self.pdf_w / img_w
        fy = self.pdf_h / img_h

        pdf_x0 = rect.left() * fx
        pdf_y0 = rect.top() * fy
        pdf_x1 = rect.right() * fx
        pdf_y1 = rect.bottom() * fy

        # Clip values
        pdf_x0 = max(0.0, min(pdf_x0, self.pdf_w))
        pdf_y0 = max(0.0, min(pdf_y0, self.pdf_h))
        pdf_x1 = max(0.0, min(pdf_x1, self.pdf_w))
        pdf_y1 = max(0.0, min(pdf_y1, self.pdf_h))

        return (pdf_x0, pdf_y0, pdf_x1, pdf_y1)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()
        elif event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


class RotateLabel(QLabel):
    angle_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_pixmap = None
        self.current_angle = 0.0
        self.is_dragging = False
        self.angle_offset = 0.0
        self.diagonal = 100
        self.setFixedSize(self.diagonal, self.diagonal)
        self.setAlignment(Qt.AlignCenter)

    def set_pixmap(self, pixmap):
        self.original_pixmap = pixmap
        # Calculate bounding size (diagonal)
        w = pixmap.width()
        h = pixmap.height()
        self.diagonal = int((w**2 + h**2)**0.5) + 20
        self.setFixedSize(self.diagonal, self.diagonal)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.original_pixmap is not None:
            self.is_dragging = True
            cx = self.width() / 2.0
            cy = self.height() / 2.0
            pos = event.position()
            dx = pos.x() - cx
            dy = pos.y() - cy
            
            import math
            mouse_angle = math.degrees(math.atan2(dy, dx))
            self.angle_offset = self.current_angle - mouse_angle
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_dragging and self.original_pixmap is not None:
            cx = self.width() / 2.0
            cy = self.height() / 2.0
            pos = event.position()
            dx = pos.x() - cx
            dy = pos.y() - cy
            
            import math
            mouse_angle = math.degrees(math.atan2(dy, dx))
            new_angle = mouse_angle + self.angle_offset
            
            # Normalize to -180 to 180
            new_angle = (new_angle + 180) % 360 - 180
            
            self.current_angle = new_angle
            self.angle_changed.emit(self.current_angle)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False
            self.update()

    def paintEvent(self, event):
        if self.original_pixmap is None:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        cx = self.width() / 2.0
        cy = self.height() / 2.0

        # 1. Draw static background alignment grid
        painter.save()
        grid_pen = QPen(QColor(128, 128, 128, 40), 1, Qt.DashLine)
        painter.setPen(grid_pen)
        grid_spacing = 40
        for x in range(grid_spacing, self.width(), grid_spacing):
            painter.drawLine(x, 0, x, self.height())
        for y in range(grid_spacing, self.height(), grid_spacing):
            painter.drawLine(0, y, self.width(), y)
        painter.restore()

        # 2. Draw rotated image
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.current_angle)

        pw = self.original_pixmap.width()
        ph = self.original_pixmap.height()
        px = -pw / 2.0
        py = -ph / 2.0
        painter.drawPixmap(QPointF(px, py), self.original_pixmap)

        # 3. Draw Axis (Trục xoay)
        # Vertical axis line from center to slightly above top edge of the image
        axis_y = py - 35
        axis_pen = QPen(QColor(0, 122, 255), 2)
        painter.setPen(axis_pen)
        painter.drawLine(QPointF(0, 0), QPointF(0, axis_y))

        # Handle circle at the end of the axis
        painter.setBrush(QColor(0, 122, 255))
        painter.drawEllipse(QPointF(0, axis_y), 7, 7)

        # Center pivot dot
        painter.setBrush(QColor(255, 59, 48))
        painter.setPen(QPen(QColor(255, 255, 255), 1.5))
        painter.drawEllipse(QPointF(0, 0), 4.5, 4.5)

        painter.restore()


class RotateDialog(QDialog):
    def __init__(self, full_pixmap, initial_angle, parent=None):
        super().__init__(parent)
        self.full_pixmap = full_pixmap
        self.initial_angle = initial_angle
        self.current_angle = initial_angle
        self.is_updating_ui = False

        self.setWindowTitle("Xoay ảnh (Rotate Page)")
        
        self.init_ui()
        
        # Set window flags and show full screen
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.showFullScreen()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 1. Top Panel for Controls & Instructions
        top_panel = QFrame(self)
        top_panel.setObjectName("TopPanel")
        
        main_win = self.parent()
        is_dark = getattr(main_win, "current_theme", "light") == "dark"
        if is_dark:
            top_panel.setStyleSheet("background-color: #1a1a20; border: 1px solid #2d2d34; border-radius: 6px; min-height: 40px;")
        else:
            top_panel.setStyleSheet("background-color: #ffffff; border: 1px solid #d1d1d6; border-radius: 6px; min-height: 40px;")

        top_layout = QHBoxLayout(top_panel)
        top_layout.setContentsMargins(10, 4, 10, 4)
        top_layout.setSpacing(10)

        lbl_instruct = QLabel("Kéo chuột trên ảnh để xoay hoặc chỉnh thanh trượt. [Enter] Lưu, [Esc] Hủy.", self)
        lbl_instruct.setStyleSheet("font-weight: bold; font-size: 11px;" + ("color: #e2e2e6;" if is_dark else "color: #1c1c1e;"))
        top_layout.addWidget(lbl_instruct)
        
        # Add angle adjustment controls: Slider & SpinBox
        lbl_angle = QLabel("Góc (độ):", self)
        lbl_angle.setStyleSheet("font-weight: bold; font-size: 11px;" + ("color: #e2e2e6;" if is_dark else "color: #1c1c1e;"))
        top_layout.addWidget(lbl_angle)

        self.slider_angle = QSlider(Qt.Horizontal, self)
        self.slider_angle.setRange(-180, 180)
        self.slider_angle.setValue(int(round(self.initial_angle)))
        self.slider_angle.setFixedWidth(150)
        top_layout.addWidget(self.slider_angle)

        self.spin_angle = QDoubleSpinBox(self)
        self.spin_angle.setRange(-180.0, 180.0)
        self.spin_angle.setDecimals(1)
        self.spin_angle.setSingleStep(0.5)
        self.spin_angle.setValue(self.initial_angle)
        self.spin_angle.setFixedWidth(70)
        if is_dark:
            self.spin_angle.setStyleSheet("background-color: #121216; color: #e2e2e6; border: 1px solid #2d2d34;")
        else:
            self.spin_angle.setStyleSheet("background-color: #ffffff; color: #1c1c1e; border: 1px solid #d1d1d6;")
        top_layout.addWidget(self.spin_angle)

        # Connect synchronization
        self.slider_angle.valueChanged.connect(self.on_slider_changed)
        self.spin_angle.valueChanged.connect(self.on_spin_changed)

        top_layout.addStretch()

        # Reset button
        btn_reset = QPushButton("Đặt lại (0°)", self)
        btn_reset.setFixedWidth(90)
        btn_reset.setStyleSheet("background-color: #f2f2f7; color: #1c1c1e;" if not is_dark else "background-color: #2a2a32; color: #e2e2e6;")
        btn_reset.clicked.connect(self.on_reset)
        top_layout.addWidget(btn_reset)

        # Cancel button
        btn_cancel = QPushButton("Hủy (Esc)", self)
        btn_cancel.setFixedWidth(90)
        btn_cancel.setStyleSheet("background-color: #f2f2f7; color: #1c1c1e;" if not is_dark else "background-color: #2a2a32; color: #e2e2e6;")
        btn_cancel.clicked.connect(self.reject)
        top_layout.addWidget(btn_cancel)

        # OK button
        btn_ok = QPushButton("OK (Enter)", self)
        btn_ok.setFixedWidth(95)
        if is_dark:
            btn_ok.setStyleSheet("background-color: #d9383a; color: white; font-weight: bold;")
        else:
            btn_ok.setStyleSheet("background-color: #ff3b30; color: white; font-weight: bold;")
        btn_ok.clicked.connect(self.accept)
        top_layout.addWidget(btn_ok)

        layout.addWidget(top_panel)

        # 2. Scroll area containing the centered image
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        if is_dark:
            self.scroll_area.setStyleSheet("background-color: #0c0c0e; border: 1px solid #2d2d34;")
        else:
            self.scroll_area.setStyleSheet("background-color: #e5e5ea; border: 1px solid #d1d1d6;")

        container = QWidget()
        container.setObjectName("ScrollContainer")
        container.setStyleSheet("background-color: transparent;")
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setAlignment(Qt.AlignCenter)

        self.rotate_label = RotateLabel(container)
        self.rotate_label.current_angle = self.initial_angle
        self.rotate_label.angle_changed.connect(self.on_label_angle_changed)
        
        container_layout.addWidget(self.rotate_label)
        self.scroll_area.setWidget(container)
        layout.addWidget(self.scroll_area)

    def showEvent(self, event):
        super().showEvent(event)
        self.scale_image_to_fit()

    def scale_image_to_fit(self):
        w = self.scroll_area.viewport().width()
        h = self.scroll_area.viewport().height()
        
        if w < 100 or h < 100:
            screen = QApplication.primaryScreen().geometry()
            w = screen.width() - 80
            h = screen.height() - 150
            
        max_w = w - 20
        max_h = h - 20
        
        orig_w = self.full_pixmap.width()
        orig_h = self.full_pixmap.height()
        orig_diag = (orig_w**2 + orig_h**2)**0.5
        
        scale = min(max_w, max_h) / orig_diag
        
        scaled_w = int(orig_w * scale)
        scaled_h = int(orig_h * scale)
        
        self.scaled_pixmap = self.full_pixmap.scaled(scaled_w, scaled_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.rotate_label.set_pixmap(self.scaled_pixmap)

    def on_slider_changed(self, val):
        if self.is_updating_ui:
            return
        self.is_updating_ui = True
        self.spin_angle.setValue(float(val))
        self.rotate_label.current_angle = float(val)
        self.rotate_label.update()
        self.current_angle = float(val)
        self.is_updating_ui = False

    def on_spin_changed(self, val):
        if self.is_updating_ui:
            return
        self.is_updating_ui = True
        self.slider_angle.setValue(int(round(val)))
        self.rotate_label.current_angle = val
        self.rotate_label.update()
        self.current_angle = val
        self.is_updating_ui = False

    def on_label_angle_changed(self, val):
        if self.is_updating_ui:
            return
        self.is_updating_ui = True
        self.spin_angle.setValue(val)
        self.slider_angle.setValue(int(round(val)))
        self.current_angle = val
        self.is_updating_ui = False

    def on_reset(self):
        self.is_updating_ui = True
        self.spin_angle.setValue(0.0)
        self.slider_angle.setValue(0)
        self.rotate_label.current_angle = 0.0
        self.rotate_label.update()
        self.current_angle = 0.0
        self.is_updating_ui = False

    def get_rotation_angle(self):
        return self.current_angle

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()
        elif event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


# Main window of the application
class PDFSplitterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bộ Xử Lý & Tách File PDF Chuyên Nghiệp")
        self.setMinimumSize(1024, 768)

        # Core logic components
        self.processor = PDFProcessor()
        self.load_worker = None
        self.current_hop_name = ""
        self.current_ho_so_name = ""
        self.current_ho_so_path = ""
        self.current_grid_mode = "3x3"

        # Load settings
        self.settings = QSettings("SuperPDFSplitter", "Settings")
        self.current_theme = self.settings.value("theme", "light")
        
        self.init_ui()
        self.load_saved_paths()
        
        if self.current_theme == "dark":
            self.apply_dark_theme()
        else:
            self.apply_light_theme()

    def init_ui(self):
        # Main central widget
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # Single compact Top Bar (occupies ~5% of screen height)
        top_bar = QFrame(self)
        top_bar.setObjectName("TopBar")
        top_bar.setFixedHeight(34)
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(6, 2, 6, 2)
        top_bar_layout.setSpacing(6)

        # 1. Sidebar Toggle
        self.btn_toggle_sidebar = QPushButton("◀ Cây thư mục", self)
        self.btn_toggle_sidebar.setFixedWidth(90)
        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)
        top_bar_layout.addWidget(self.btn_toggle_sidebar)

        top_bar_layout.addWidget(self.create_v_line())

        # 2. Input
        lbl_input = QLabel("Input:", self)
        lbl_input.setStyleSheet("font-weight: bold;")
        self.txt_input = QLineEdit(self)
        self.txt_input.setReadOnly(True)
        self.txt_input.setPlaceholderText("Chọn thư mục đầu vào...")
        btn_browse_input = QPushButton("...", self)
        btn_browse_input.setToolTip("Chọn thư mục Input")
        btn_browse_input.setFixedWidth(24)
        btn_browse_input.clicked.connect(self.browse_input)
        top_bar_layout.addWidget(lbl_input)
        top_bar_layout.addWidget(self.txt_input, stretch=2)
        top_bar_layout.addWidget(btn_browse_input)

        top_bar_layout.addWidget(self.create_v_line())

        # 3. Output
        lbl_output = QLabel("Output:", self)
        lbl_output.setStyleSheet("font-weight: bold;")
        self.txt_output = QLineEdit(self)
        self.txt_output.setReadOnly(True)
        self.txt_output.setPlaceholderText("Chọn thư mục đầu ra...")
        btn_browse_output = QPushButton("...", self)
        btn_browse_output.setToolTip("Chọn thư mục Output")
        btn_browse_output.setFixedWidth(24)
        btn_browse_output.clicked.connect(self.browse_output)
        top_bar_layout.addWidget(lbl_output)
        top_bar_layout.addWidget(self.txt_output, stretch=2)
        top_bar_layout.addWidget(btn_browse_output)

        top_bar_layout.addWidget(self.create_v_line())

        # 4. Grid view mode
        lbl_grid = QLabel("Lưới:", self)
        lbl_grid.setStyleSheet("font-weight: bold;")
        self.cb_grid_mode = QComboBox(self)
        self.cb_grid_mode.addItems(list(GRID_MODES.keys()))
        self.cb_grid_mode.setCurrentText(self.current_grid_mode)
        self.cb_grid_mode.currentTextChanged.connect(self.change_grid_mode)
        self.cb_grid_mode.setFixedWidth(50)
        top_bar_layout.addWidget(lbl_grid)
        top_bar_layout.addWidget(self.cb_grid_mode)

        top_bar_layout.addWidget(self.create_v_line())

        # 5. Active dossier indicator
        self.lbl_active_hoso = QLabel("Hồ sơ: Chưa chọn", self)
        self.lbl_active_hoso.setObjectName("lblActiveHoso")
        self.lbl_active_hoso.setStyleSheet("font-weight: bold; color: #007aff;")
        top_bar_layout.addWidget(self.lbl_active_hoso, stretch=1)

        top_bar_layout.addWidget(self.create_v_line())

        # Theme toggle button
        self.btn_theme = QPushButton("🌙" if self.current_theme == "light" else "☀️", self)
        self.btn_theme.setToolTip("Đổi giao diện Sáng/Tối")
        self.btn_theme.setFixedWidth(24)
        self.btn_theme.clicked.connect(self.toggle_theme)
        top_bar_layout.addWidget(self.btn_theme)

        top_bar_layout.addWidget(self.create_v_line())

        # 6. Splitting action button
        self.btn_split = QPushButton("✂️ Ngắt File", self)
        self.btn_split.setObjectName("btnSplit")
        self.btn_split.setFixedWidth(90)
        self.btn_split.clicked.connect(self.on_split_clicked)
        top_bar_layout.addWidget(self.btn_split)

        main_layout.addWidget(top_bar)

        # ----------------- 3. Main Area Splitter (Sidebar | Viewer) -----------------
        self.splitter = QSplitter(Qt.Horizontal, self)
        
        # Left Panel (Sidebar Tree Folder)
        self.sidebar_widget = QWidget(self)
        self.sidebar_widget.setObjectName("SidebarWidget")
        sidebar_layout = QVBoxLayout(self.sidebar_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(6)

        sidebar_header = QHBoxLayout()
        sidebar_header.addWidget(QLabel("CÂY THƯ MỤC HỒ SƠ", self))
        sidebar_header.addStretch()
        
        # Refresh button
        btn_refresh_tree = QPushButton("🔄", self)
        btn_refresh_tree.setToolTip("Tải lại danh sách thư mục")
        btn_refresh_tree.setFixedHeight(22)
        btn_refresh_tree.setFixedWidth(24)
        btn_refresh_tree.setStyleSheet("font-size: 11px; padding: 2px;")
        btn_refresh_tree.clicked.connect(self.refresh_tree)
        sidebar_header.addWidget(btn_refresh_tree)
        
        # Collapse all tree nodes button
        btn_collapse_tree = QPushButton("Thu gọn", self)
        btn_collapse_tree.setFixedHeight(22)
        btn_collapse_tree.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        btn_collapse_tree.clicked.connect(self.collapse_tree)
        sidebar_header.addWidget(btn_collapse_tree)
        sidebar_layout.addLayout(sidebar_header)

        # Folder Tree View
        self.tree_view = QTreeView(self)
        self.tree_view.setHeaderHidden(True)
        self.tree_model = QStandardItemModel()
        self.tree_view.setModel(self.tree_model)
        self.tree_view.clicked.connect(self.on_tree_clicked)
        sidebar_layout.addWidget(self.tree_view)

        self.splitter.addWidget(self.sidebar_widget)

        # Right Panel (Grid Thumbnail View)
        right_container = QWidget(self)
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)

        # Loading status indicator
        self.lbl_status = QLabel("Vui lòng chọn một hồ sơ trên danh mục để bắt đầu.", self)
        self.lbl_status.setObjectName("lblStatus")
        self.lbl_status.setStyleSheet("padding-left: 5px;")
        right_layout.addWidget(self.lbl_status)

        # Scroll area enclosing the grid
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("ScrollArea")
        
        self.grid_widget = PageGridWidget(self.scroll_area)
        self.grid_widget.setObjectName("GridContainer")
        self.grid_widget.reordered.connect(self.handle_reorder)
        self.scroll_area.setWidget(self.grid_widget)
        
        right_layout.addWidget(self.scroll_area)
        
        self.splitter.addWidget(right_container)

        # Set default splitter ratio (narrow sidebar, wider grid workspace)
        self.splitter.setSizes([180, 844])
        main_layout.addWidget(self.splitter)

        # Show as full screen on launch
        self.showMaximized()

    def create_v_line(self):
        line = QFrame(self)
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("color: #d1d1d6; max-width: 1px; min-height: 16px;")
        return line

    # Load paths on launch
    def load_saved_paths(self):
        pass

    # Browse Directory Actions
    def browse_input(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Chọn thư mục INPUT")
        if dir_path:
            self.txt_input.setText(dir_path)
            self.populate_tree_model(dir_path)

    def browse_output(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Chọn thư mục OUTPUT")
        if dir_path:
            self.txt_output.setText(dir_path)
            self.update_tree_checkmarks()

    # Populates Tree containing only Box/Profile subfolders
    def populate_tree_model(self, input_dir):
        self.tree_model.clear()
        self.tree_model.setHorizontalHeaderLabels(["Cây thư mục"])
        
        if not input_dir or not os.path.exists(input_dir):
            return

        try:
            # 1st level: Boxes ("hộp")
            boxes = sorted([d for d in os.listdir(input_dir) if os.path.isdir(os.path.join(input_dir, d))])
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể đọc thư mục đầu vào:\n{e}")
            return

        for box in boxes:
            box_path = os.path.join(input_dir, box)
            box_item = QStandardItem(box)
            box_item.setData(box_path, Qt.UserRole)
            box_item.setEditable(False)
            box_item.setSelectable(False)  # Users should only select Dossiers, not Boxes

            try:
                # 2nd level: Profiles ("hồ sơ")
                dossiers = sorted([d for d in os.listdir(box_path) if os.path.isdir(os.path.join(box_path, d))])
            except Exception:
                dossiers = []

            for dossier in dossiers:
                dossier_path = os.path.join(box_path, dossier)
                
                # Count if it has any PDF files in it
                pdf_files = [f for f in os.listdir(dossier_path) if f.lower().endswith('.pdf')]
                pdf_tag = f" ({len(pdf_files)} file PDF)" if pdf_files else " (Trống)"
                
                dossier_item = QStandardItem(f"{dossier}{pdf_tag}")
                dossier_item.setData(dossier_path, Qt.UserRole)
                dossier_item.setEditable(False)
                box_item.appendRow(dossier_item)

            if box_item.rowCount() > 0:
                self.tree_model.appendRow(box_item)

        # Expand top items by default
        self.tree_view.expandAll()
        self.update_tree_checkmarks()

    def update_tree_checkmarks(self):
        input_dir = self.txt_input.text().strip()
        output_dir = self.txt_output.text().strip()
        if not input_dir or not os.path.exists(input_dir):
            return

        for row in range(self.tree_model.rowCount()):
            box_item = self.tree_model.item(row)
            if not box_item:
                continue
            for child_row in range(box_item.rowCount()):
                dossier_item = box_item.child(child_row)
                if not dossier_item:
                    continue
                dossier_path = dossier_item.data(Qt.UserRole)
                if not dossier_path or not os.path.exists(dossier_path):
                    continue

                dossier_name = os.path.basename(dossier_path)
                try:
                    pdf_files = [f for f in os.listdir(dossier_path) if f.lower().endswith('.pdf')]
                    pdf_tag = f" ({len(pdf_files)} file PDF)" if pdf_files else " (Trống)"
                except Exception:
                    pdf_tag = " (Trống)"

                # Check if output exists and is not empty
                has_output = False
                if output_dir and os.path.exists(output_dir):
                    rel_path = os.path.relpath(dossier_path, input_dir)
                    target_output_dir = os.path.join(output_dir, rel_path)
                    if os.path.exists(target_output_dir):
                        try:
                            if os.listdir(target_output_dir):
                                has_output = True
                        except Exception:
                            pass

                if has_output:
                    dossier_item.setText(f"{dossier_name}{pdf_tag} ✅")
                else:
                    dossier_item.setText(f"{dossier_name}{pdf_tag}")

    # Toggle sidebar visibility
    def toggle_sidebar(self):
        visible = self.sidebar_widget.isVisible()
        self.sidebar_widget.setVisible(not visible)
        if visible:
            self.btn_toggle_sidebar.setText("▶ Thư mục")
        else:
            self.btn_toggle_sidebar.setText("◀ Thư mục")

    def collapse_tree(self):
        self.tree_view.collapseAll()

    def refresh_tree(self):
        input_dir = self.txt_input.text().strip()
        if input_dir and os.path.exists(input_dir):
            self.populate_tree_model(input_dir)
            self.lbl_status.setText("Đã cập nhật lại danh sách thư mục hồ sơ.")

    # Handles folder selection in sidebar
    def on_tree_clicked(self, index):
        item = self.tree_model.itemFromIndex(index)
        if not item:
            return

        parent = item.parent()
        if parent is not None:
            # Selected item is a dossier (since it has a box parent)
            dossier_path = item.data(Qt.UserRole)
            dossier_name_with_tag = item.text()
            
            # Clean the tag (number of pdf files) off the name for display
            dossier_name = re.sub(r'\s*\(\d+ file PDF\)$', '', dossier_name_with_tag)
            dossier_name = re.sub(r'\s*\(Trống\)$', '', dossier_name)
            
            box_name = parent.text()

            self.current_hop_name = box_name
            self.current_ho_so_name = dossier_name
            self.current_ho_so_path = dossier_path
            
            self.lbl_active_hoso.setText(f"Hồ sơ đang chọn: {box_name} ➔ {dossier_name}")
            self.load_ho_so_pages(dossier_path)

    # Dispatches thread to load pages asynchronously
    def load_ho_so_pages(self, dossier_path):
        # Terminate any running loader thread first
        if self.load_worker and self.load_worker.isRunning():
            self.load_worker.cancel()
            self.load_worker.wait()

        self.processor.clear()
        self.grid_widget.clear_grid()
        self.scroll_area.verticalScrollBar().setValue(0)
        self.scroll_area.horizontalScrollBar().setValue(0)
        self.lbl_status.setText("Đang tải dữ liệu...")

        self.load_worker = PageLoadWorker(dossier_path)
        self.load_worker.page_loaded.connect(self.handle_page_loaded)
        self.load_worker.progress_status.connect(self.lbl_status.setText)
        self.load_worker.finished.connect(self.handle_load_finished)
        self.load_worker.start()

    def handle_page_loaded(self, idx, qimg, page_info):
        # Convert QImage to QPixmap on GUI thread (Required by Qt)
        pixmap = QPixmap.fromImage(qimg)
        page_info["pixmap"] = pixmap
        page_info["id"] = idx

        self.processor.pages.append(page_info)

        # Create page widget
        cols, width = GRID_MODES[self.current_grid_mode]
        widget = PageWidget(page_info, target_width=width, parent=self.grid_widget)
        widget.clicked.connect(self.toggle_breakpoint)
        widget.rotate_requested.connect(self.rotate_page)
        widget.delete_requested.connect(self.delete_page)
        widget.crop_requested.connect(self.open_crop_dialog)
        widget.rotate_angle_requested.connect(self.open_rotate_dialog)
        widget.clean_borders_requested.connect(self.toggle_clean_borders)

        self.grid_widget.widgets.append(widget)
        widget.index = len(self.grid_widget.widgets) - 1
        widget.update_display()

        row = widget.index // self.grid_widget.columns
        col = widget.index % self.grid_widget.columns
        self.grid_widget.grid_layout.addWidget(widget, row, col)

    def handle_load_finished(self):
        total_loaded = len([p for p in self.processor.pages if not p["is_deleted"]])
        self.lbl_status.setText(f"Đã tải xong {total_loaded} trang. Nhấn vào ảnh để đặt điểm ngắt, kéo thả để đổi thứ tự.")

    # Grid mode switching logic
    def change_grid_mode(self, mode_name):
        if mode_name not in GRID_MODES:
            return
        self.current_grid_mode = mode_name
        cols, width = GRID_MODES[mode_name]
        
        self.grid_widget.columns = cols
        for widget in self.grid_widget.widgets:
            widget.target_width = width
            widget.update_display()
            
        self.grid_widget.rearrange_grid()

    # Re-order logic triggered from drag & drop drops
    def handle_reorder(self, src_idx, dst_idx):
        self.processor.reorder_pages(src_idx, dst_idx)
        
        # Synchronize UI widgets order with logic lists
        widgets = self.grid_widget.widgets
        widget_to_move = widgets.pop(src_idx)
        widgets.insert(dst_idx, widget_to_move)
        
        self.grid_widget.rearrange_grid()

    # Click on page: Toggle breakpoint splits
    def toggle_breakpoint(self, visible_idx):
        # Map visible index to internal processor page info
        visible_pages = [p for p in self.processor.pages if not p["is_deleted"]]
        if visible_idx >= len(visible_pages):
            return
            
        target_page = visible_pages[visible_idx]
        target_page["has_breakpoint"] = not target_page["has_breakpoint"]
        
        # Refresh visual representation on this widget
        self.grid_widget.widgets[visible_idx].update_state()

    # Rotate single page
    def rotate_page(self, page_id, delta):
        # Find page in processor
        target_page = None
        for p in self.processor.pages:
            if p["id"] == page_id:
                target_page = p
                break
        if not target_page:
            return

        # Add rotation (0, 90, 180, 270)
        target_page["rotation"] = (target_page["rotation"] + delta) % 360
        
        # Update matching widget
        visible_idx = 0
        for p in self.processor.pages:
            if p["is_deleted"]:
                continue
            if p["id"] == page_id:
                self.grid_widget.widgets[visible_idx].update_display()
                break
            visible_idx += 1

    def toggle_clean_borders(self, page_id):
        # Find page info
        page_info = None
        for p in self.processor.pages:
            if p["id"] == page_id:
                page_info = p
                break
        if not page_info:
            return
            
        if "white_borders" in page_info:
            # Toggle off
            del page_info["white_borders"]
        else:
            # Toggle on: detect borders
            qimg = page_info["pixmap"].toImage()
            ratios = detect_black_borders(qimg)
            page_info["white_borders"] = ratios
            
        # Update matching widget
        visible_idx = 0
        for p in self.processor.pages:
            if p["is_deleted"]:
                continue
            if p["id"] == page_id:
                self.grid_widget.widgets[visible_idx].update_state()
                break
            visible_idx += 1

    # Delete single page (only removes it from layout/out, keeps original safe)
    def delete_page(self, page_id):
        # Mark as deleted in processor logic
        target_page = None
        for p in self.processor.pages:
            if p["id"] == page_id:
                target_page = p
                break
        if not target_page:
            return
            
        target_page["is_deleted"] = True

        # Remove from UI grid widget list
        visible_idx = -1
        for idx, widget in enumerate(self.grid_widget.widgets):
            if widget.page_id == page_id:
                visible_idx = idx
                break

        if visible_idx != -1:
            widget_to_delete = self.grid_widget.widgets.pop(visible_idx)
            self.grid_widget.grid_layout.removeWidget(widget_to_delete)
            widget_to_delete.deleteLater()
            
            # Rearrange grid positions and numbers
            self.grid_widget.rearrange_grid()
            
        total_remaining = len([p for p in self.processor.pages if not p["is_deleted"]])
        self.lbl_status.setText(f"Đã xóa trang. Còn lại {total_remaining} trang.")

    def open_crop_dialog(self, page_id):
        # Find page info
        page_info = None
        for p in self.processor.pages:
            if p["id"] == page_id:
                page_info = p
                break
        if not page_info:
            return

        # Render high-res full page for cropping (using PyMuPDF)
        try:
            doc = fitz.open(page_info["source_pdf"])
            page = doc[page_info["original_page_index"]]
            
            # Original PDF page dimensions
            pdf_w = page.rect.width
            pdf_h = page.rect.height
            
            # Render at 150 DPI for sharp full screen view
            zoom = 150 / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            full_pixmap = QPixmap.fromImage(qimg)
            doc.close()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể tải trang để cắt:\n{e}")
            return
            
        # Open dialog
        dialog = CropDialog(full_pixmap, pdf_w, pdf_h, self)
        if dialog.exec() == QDialog.Accepted:
            crop_rect = dialog.get_mapped_crop_rect()
            if crop_rect == -1:
                # No new drag selection, do nothing
                return
            elif crop_rect is None:
                # Reset crop requested
                if "crop_rect" in page_info:
                    del page_info["crop_rect"]
            else:
                # Valid crop rectangle mapped
                page_info["crop_rect"] = crop_rect

            # Re-render the thumbnail pixmap in page_info
            page_info["pixmap"] = self.render_cropped_thumbnail(page_info)
            
            # Update the page widget display!
            visible_idx = 0
            for p in self.processor.pages:
                if p["is_deleted"]:
                    continue
                if p["id"] == page_id:
                    self.grid_widget.widgets[visible_idx].update_state()
                    break
                visible_idx += 1

    def render_cropped_thumbnail(self, page_info):
        try:
            doc = fitz.open(page_info["source_pdf"])
            page = doc[page_info["original_page_index"]]
            zoom = 150 / 72
            mat = fitz.Matrix(zoom, zoom)
            
            c = page_info.get("crop_rect")
            if c:
                clip_rect = fitz.Rect(c[0], c[1], c[2], c[3])
                pix = page.get_pixmap(matrix=mat, clip=clip_rect, alpha=False)
            else:
                pix = page.get_pixmap(matrix=mat, alpha=False)
                
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            pixmap = QPixmap.fromImage(qimg)
            doc.close()
            return pixmap
        except Exception as e:
            print(f"Error rendering thumbnail: {e}")
            return page_info["pixmap"] # Fallback to existing

    def open_rotate_dialog(self, page_id):
        # Find page info
        page_info = None
        for p in self.processor.pages:
            if p["id"] == page_id:
                page_info = p
                break
        if not page_info:
            return

        # Render high-res full page for rotation view (using PyMuPDF)
        try:
            doc = fitz.open(page_info["source_pdf"])
            page = doc[page_info["original_page_index"]]
            
            # Original PDF page dimensions
            pdf_w = page.rect.width
            pdf_h = page.rect.height
            
            # Render at 150 DPI for sharp full screen view
            zoom = 150 / 72
            mat = fitz.Matrix(zoom, zoom)
            
            # If the page is cropped, render only the crop area.
            c = page_info.get("crop_rect")
            if c:
                clip_rect = fitz.Rect(c[0], c[1], c[2], c[3])
                pix = page.get_pixmap(matrix=mat, clip=clip_rect, alpha=False)
            else:
                pix = page.get_pixmap(matrix=mat, alpha=False)
                
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            full_pixmap = QPixmap.fromImage(qimg)
            doc.close()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể tải trang để xoay:\n{e}")
            return
            
        # Open dialog
        dialog = RotateDialog(full_pixmap, page_info.get("custom_angle", 0.0), self)
        if dialog.exec() == QDialog.Accepted:
            angle = dialog.get_rotation_angle()
            page_info["custom_angle"] = angle
            
            # Update the page widget display!
            visible_idx = 0
            for p in self.processor.pages:
                if p["is_deleted"]:
                    continue
                if p["id"] == page_id:
                    self.grid_widget.widgets[visible_idx].update_state()
                    break
                visible_idx += 1

    # Split Operation with Duplicate Checks
    def on_split_clicked(self):
        if not self.current_ho_so_path:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng chọn hồ sơ bên cây thư mục trước.")
            return

        output_dir = self.txt_output.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng cấu hình thư mục Output.")
            return

        hop_name = self.current_hop_name
        ho_so_name = self.current_ho_so_name
        target_dir = os.path.join(output_dir, hop_name, ho_so_name)

        # Duplicate folder checking and warnings
        if os.path.exists(target_dir):
            existing_files = [f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f))]
            if existing_files:
                reply = QMessageBox.question(
                    self,
                    "Xác nhận ghi đè",
                    f"Thư mục '{hop_name}/{ho_so_name}' trong thư mục Output đã tồn tại các file cũ.\n"
                    "Bạn có muốn XÓA HẾT các file cũ này để tạo mới hoàn toàn không?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    try:
                        for item in os.listdir(target_dir):
                            item_path = os.path.join(target_dir, item)
                            if os.path.isfile(item_path):
                                os.remove(item_path)
                            elif os.path.isdir(item_path):
                                shutil.rmtree(item_path)
                    except Exception as e:
                        QMessageBox.critical(self, "Lỗi", f"Không thể xóa thư mục cũ:\n{str(e)}")
                        return
                else:
                    # Operation cancelled by user
                    return

        # Perform PDF splitting
        success, msg = self.processor.split_pdf(output_dir, hop_name, ho_so_name)
        if success:
            self.update_tree_checkmarks()
            QMessageBox.information(self, "Thành công", msg)
        else:
            QMessageBox.critical(self, "Lỗi", f"Tách file PDF thất bại:\n{msg}")

    # Stylesheet for professional Light Theme layout aesthetics (Mac/iOS style)
    def apply_light_theme(self):
        qss = """
        QMainWindow {
            background-color: #f5f5f7;
        }
        
        QSplitter::handle {
            background-color: #e5e5ea;
        }
        
        QFrame#TopBar, QFrame#ControlBar {
            background-color: #ffffff;
            border: 1px solid #d1d1d6;
            border-radius: 6px;
        }
        
        QWidget#SidebarWidget {
            background-color: #f5f5f7;
        }
        
        QTreeView {
            background-color: #ffffff;
            color: #1c1c1e;
            border: 1px solid #d1d1d6;
            border-radius: 6px;
            padding: 5px;
            font-size: 11px;
        }
        
        QTreeView::item {
            padding: 4px;
            border-radius: 3px;
        }
        
        QTreeView::item:hover {
            background-color: #f2f2f7;
        }
        
        QTreeView::item:selected {
            background-color: #007aff;
            color: #ffffff;
            font-weight: bold;
        }
        
        QScrollArea#ScrollArea {
            border: 1px solid #d1d1d6;
            border-radius: 6px;
            background-color: #e5e5ea;
        }
        
        QWidget#GridContainer {
            background-color: #e5e5ea;
        }
        
        QLineEdit {
            background-color: #ffffff;
            color: #1c1c1e;
            border: 1px solid #d1d1d6;
            border-radius: 4px;
            padding: 3px 6px;
            font-size: 11px;
        }
        
        QComboBox {
            background-color: #ffffff;
            color: #1c1c1e;
            border: 1px solid #d1d1d6;
            border-radius: 4px;
            padding: 2px 6px;
            min-width: 70px;
            font-size: 11px;
        }
        
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 16px;
            border-left-width: 1px;
            border-left-color: #d1d1d6;
            border-left-style: solid;
        }
        
        QPushButton {
            background-color: #ffffff;
            color: #1c1c1e;
            border: 1px solid #d1d1d6;
            border-radius: 4px;
            padding: 3px 8px;
            font-weight: bold;
            font-size: 11px;
        }
        
        QPushButton:hover {
            background-color: #f2f2f7;
            border-color: #c7c7cc;
        }
        
        QPushButton:pressed {
            background-color: #e5e5ea;
        }
        
        QPushButton#btnSplit {
            background-color: #ff3b30;
            border-color: #ff3b30;
            color: white;
            font-weight: bold;
            font-size: 12px;
        }
        
        QPushButton#btnSplit:hover {
            background-color: #ff453a;
        }
        
        QPushButton#btnSplit:pressed {
            background-color: #d72c21;
        }
        
        QPushButton#btnControl {
            background-color: #fafafa;
            border: 1px solid #d1d1d6;
            font-size: 9px;
            font-weight: normal;
            padding: 0px;
        }
        
        QPushButton#btnControl:hover {
            background-color: #007aff;
            color: white;
            border-color: #007aff;
        }
        
        QPushButton#btnDelete {
            background-color: #ffeef0;
            border: 1px solid #ffccd1;
            font-size: 9px;
            padding: 0px;
        }
        
        QPushButton#btnDelete:hover {
            background-color: #ff3b30;
            color: white;
            border-color: #ff3b30;
        }
        
        QLabel {
            color: #1c1c1e;
            font-size: 11px;
        }
        
        QLabel#lblStatus {
            color: #555555;
            font-size: 11px;
        }
        """
        self.setStyleSheet(qss)

    # Stylesheet for professional Dark Theme layout aesthetics
    def apply_dark_theme(self):
        qss = """
        QMainWindow {
            background-color: #121216;
        }
        
        QSplitter::handle {
            background-color: #25252b;
        }
        
        QFrame#TopBar {
            background-color: #1a1a20;
            border: 1px solid #2d2d34;
            border-radius: 6px;
        }
        
        QWidget#SidebarWidget {
            background-color: #121216;
        }
        
        QTreeView {
            background-color: #1a1a20;
            color: #e2e2e6;
            border: 1px solid #2d2d34;
            border-radius: 6px;
            padding: 5px;
            font-size: 11px;
        }
        
        QTreeView::item {
            padding: 4px;
            border-radius: 3px;
        }
        
        QTreeView::item:hover {
            background-color: #2b2b36;
        }
        
        QTreeView::item:selected {
            background-color: #3b5998;
            color: #ffffff;
            font-weight: bold;
        }
        
        QScrollArea#ScrollArea {
            border: 1px solid #2d2d34;
            border-radius: 6px;
            background-color: #0c0c0e;
        }
        
        QWidget#GridContainer {
            background-color: #0c0c0e;
        }
        
        QLineEdit {
            background-color: #121216;
            color: #e2e2e6;
            border: 1px solid #2d2d34;
            border-radius: 4px;
            padding: 3px 6px;
            font-size: 11px;
        }
        
        QComboBox {
            background-color: #2a2a32;
            color: #e2e2e6;
            border: 1px solid #3d3d46;
            border-radius: 4px;
            padding: 2px 6px;
            min-width: 70px;
            font-size: 11px;
        }
        
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 16px;
            border-left-width: 1px;
            border-left-color: #3d3d46;
            border-left-style: solid;
        }
        
        QPushButton {
            background-color: #2a2a32;
            color: #e2e2e6;
            border: 1px solid #3d3d46;
            border-radius: 4px;
            padding: 3px 8px;
            font-weight: bold;
            font-size: 11px;
        }
        
        QPushButton:hover {
            background-color: #363640;
            border-color: #50505b;
        }
        
        QPushButton:pressed {
            background-color: #1a1a20;
        }
        
        QPushButton#btnSplit {
            background-color: #d9383a;
            border-color: #e84a4c;
            color: white;
            font-weight: bold;
            font-size: 12px;
        }
        
        QPushButton#btnSplit:hover {
            background-color: #e84a4c;
        }
        
        QPushButton#btnSplit:pressed {
            background-color: #b22d2f;
        }
        
        QPushButton#btnControl {
            background-color: #25252b;
            border: 1px solid #3d3d46;
            font-size: 9px;
            font-weight: normal;
            padding: 0px;
        }
        
        QPushButton#btnControl:hover {
            background-color: #3b5998;
            color: white;
            border-color: #3b5998;
        }
        
        QPushButton#btnDelete {
            background-color: #2b1d1f;
            border: 1px solid #5c2527;
            font-size: 9px;
            padding: 0px;
        }
        
        QPushButton#btnDelete:hover {
            background-color: #d9383a;
            color: white;
            border-color: #d9383a;
        }
        
        QLabel {
            color: #e2e2e6;
            font-size: 11px;
        }
        
        QLabel#lblStatus {
            color: #aaaaaa;
            font-size: 11px;
        }
        """
        self.setStyleSheet(qss)

    # Theme toggle action method
    def toggle_theme(self):
        if self.current_theme == "light":
            self.current_theme = "dark"
            self.btn_theme.setText("☀️")
            self.apply_dark_theme()
        else:
            self.current_theme = "light"
            self.btn_theme.setText("🌙")
            self.apply_light_theme()
            
        self.settings.setValue("theme", self.current_theme)
        
        # Refresh visual representation on all loaded thumbnail widgets
        for widget in self.grid_widget.widgets:
            widget.update_state()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PDFSplitterApp()
    window.show()
    sys.exit(app.exec())
