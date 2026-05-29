import os
import fitz  # PyMuPDF

def create_dummy_pdf(filename, num_pages, label):
    """Creates a dummy PDF file with a label and page numbers."""
    doc = fitz.open()
    for i in range(1, num_pages + 1):
        # Create a new page (A4 size: 595 x 842)
        page = doc.new_page(width=595, height=842)
        
        # Insert text to identify the file and page
        rect = fitz.Rect(50, 50, 550, 790)
        text = f"FILE: {label}\nPAGE: {i} / {num_pages}\n\nThis is dummy content for testing."
        
        # Use simple built-in font
        page.insert_textbox(rect, text, fontsize=24, fontname="helv", align=fitz.TEXT_ALIGN_CENTER)
        
        # Draw a border around the page
        page.draw_rect(fitz.Rect(20, 20, 575, 822), color=(0.7, 0.7, 0.7), width=2)
        
    doc.save(filename)
    doc.close()
    print(f"Created: {filename} with {num_pages} pages.")

def setup_test_structure():
    base_dir = "test_input"
    
    # Structure definition: hop -> ho_so -> list of (pdf_name, pages)
    structure = {
        "Hop_01": {
            "Ho_so_01": [("1.pdf", 3), ("2.pdf", 2)],
            "Ho_so_02": [("1.pdf", 4)],
        },
        "Hop_02": {
            "Ho_so_01": [("1.pdf", 2), ("2.pdf", 1)],
            "Ho_so_02": [("1.pdf", 5)],
        }
    }
    
    for hop, ho_sos in structure.items():
        for ho_so, files in ho_sos.items():
            dir_path = os.path.join(base_dir, hop, ho_so)
            os.makedirs(dir_path, exist_ok=True)
            for pdf_name, num_pages in files:
                file_path = os.path.join(dir_path, pdf_name)
                label = f"{hop} -> {ho_so} -> {pdf_name}"
                create_dummy_pdf(file_path, num_pages, label)

if __name__ == "__main__":
    setup_test_structure()
    print("\nDummy test structure created under './test_input'")
