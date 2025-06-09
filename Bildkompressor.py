import sys
import os
import shutil
import sqlite3
from PIL import Image
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTableView, QMessageBox,
    QDialog, QFormLayout, QSlider, QComboBox, QDialogButtonBox,
    QAbstractItemView, QStyledItemDelegate, QHeaderView, QSpinBox
)
from PyQt5.QtCore import Qt, QMimeData, QAbstractTableModel, QVariant, QModelIndex

# Constants
DB_FILE = 'images.db'
IMAGES_DIR = 'stored_images'


def ensure_images_dir():
    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR)


class ImageDatabase:
    def __init__(self, db_path=DB_FILE):
        self.conn = sqlite3.connect(db_path)
        self._create_table()

    def _create_table(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL UNIQUE
            )
        ''')
        self.conn.commit()

    def add_image(self, filename, filepath):
        cursor = self.conn.cursor()
        try:
            cursor.execute('INSERT INTO images (filename, filepath) VALUES (?,?)', (filename, filepath))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # file already exists in DB
            return None

    def get_all_images(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT id, filename, filepath FROM images ORDER BY id DESC')
        return cursor.fetchall()

    def update_image_path(self, image_id, new_filepath):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE images SET filepath=? WHERE id=?', (new_filepath, image_id))
        self.conn.commit()

    def delete_image(self, image_id):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM images WHERE id=?', (image_id,))
        self.conn.commit()


class ImageTableModel(QAbstractTableModel):
    def __init__(self, db: ImageDatabase):
        super().__init__()
        self.db = db
        self.images = []
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        self.images = self.db.get_all_images()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.images)

    def columnCount(self, parent=QModelIndex()):
        return 3  # ID, filename, filepath

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        image = self.images[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            if col == 0:
                return image[0]  # id
            elif col == 1:
                return image[1]  # filename
            elif col == 2:
                return image[2]  # filepath
        return QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        headers = ['ID', 'Filename', 'File path']
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return headers[section]
        return super().headerData(section, orientation, role)


class DragDropWidget(QWidget):
    def __init__(self, db: ImageDatabase, model: ImageTableModel):
        super().__init__()
        self.db = db
        self.model = model
        self.setAcceptDrops(True)
        self.init_ui()

    def init_ui(self):
        self.label = QLabel("Drag and drop images here")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("""
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 12px;
                font-size: 18px;
                color: #666;
                padding: 40px;
                background-color: #fafafa;
            }
            QLabel:hover {
                border-color: #555;
                color: #444;
                background-color: #f0f0f0;
            }
        """)
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            # Accept only if urls contain at least one supported image extension
            urls = event.mimeData().urls()
            for url in urls:
                if url.isLocalFile():
                    ext = os.path.splitext(url.toLocalFile())[1].lower()
                    if ext in ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp']:
                        event.acceptProposedAction()
                        return
        event.ignore()

    def dropEvent(self, event):
        files = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                filepath = url.toLocalFile()
                ext = os.path.splitext(filepath)[1].lower()
                if ext in ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp']:
                    files.append(filepath)

        if not files:
            QMessageBox.information(self, "No images", "No supported image files dropped.")
            return

        added_count = 0
        for f in files:
            filename = os.path.basename(f)
            # Copy image into IMAGES_DIR with a unique name if collision
            target_path = os.path.join(IMAGES_DIR, filename)
            base, ext = os.path.splitext(filename)
            i = 1
            while os.path.exists(target_path):
                target_path = os.path.join(IMAGES_DIR, f"{base}_{i}{ext}")
                i += 1
            try:
                shutil.copy2(f, target_path)
                if self.db.add_image(os.path.basename(target_path), target_path):
                    added_count += 1
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not add image {filename}:\n{e}")
        self.model.refresh()
        QMessageBox.information(self, "Images added", f"Successfully added {added_count} image(s).")


class CompressionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Compression Settings")
        self.setModal(True)
        self.compression_quality = 75
        self.bit_depth = 8
        self.format = 'JPEG'
        self.init_ui()

    def init_ui(self):
        form = QFormLayout()

        # Compression quality (slider 1 - 95)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(95)
        self.slider.setValue(self.compression_quality)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setTickInterval(10)
        form.addRow("Compression Quality:", self.slider)

        # Bit depth combo
        self.bit_depth_combo = QComboBox()
        self.bit_depth_combo.addItems(['1', '8', '16'])
        self.bit_depth_combo.setCurrentText(str(self.bit_depth))
        form.addRow("Bit Depth:", self.bit_depth_combo)

        # Format combo
        self.format_combo = QComboBox()
        self.format_combo.addItems(['JPEG', 'PNG', 'WEBP', 'BMP'])
        self.format_combo.setCurrentText(self.format)
        form.addRow("Output Format:", self.format_combo)

        # Buttons OK / Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        main_layout = QVBoxLayout()
        main_layout.addLayout(form)
        main_layout.addWidget(buttons)
        self.setLayout(main_layout)

    def get_values(self):
        return {
            'quality': self.slider.value(),
            'bit_depth': int(self.bit_depth_combo.currentText()),
            'format': self.format_combo.currentText()
        }


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Compressor Application")
        self.resize(900, 600)
        ensure_images_dir()
        self.db = ImageDatabase()
        self.model = ImageTableModel(self.db)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        top_layout = QHBoxLayout()

        self.dragdrop = DragDropWidget(self.db, self.model)
        self.dragdrop.setFixedHeight(180)

        # Table View for DB images
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # Compression button
        self.compress_btn = QPushButton("Compress Images")
        self.compress_btn.clicked.connect(self.open_compression_dialog)

        top_layout.addWidget(self.dragdrop)
        top_layout.addWidget(self.compress_btn)

        layout.addLayout(top_layout)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def open_compression_dialog(self):
        dialog = CompressionDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            opts = dialog.get_values()
            self.compress_all_images(opts)

    def compress_all_images(self, options):
        images = self.db.get_all_images()
        total = len(images)
        if total == 0:
            QMessageBox.information(self, "No images","No images in the database to compress.")
            return

        for image_id, filename, filepath in images:
            try:
                img = Image.open(filepath)
                # Convert bit depth
                if options['bit_depth'] == 1:
                    img = img.convert('1')  # 1-bit pixels, black and white, stored with one pixel per byte
                elif options['bit_depth'] == 8:
                    img = img.convert('L') if img.mode != 'RGB' and img.mode != 'RGBA' else img.convert('RGB')
                elif options['bit_depth'] == 16:
                    # Pillow doesn't provide direct 16-bit per channel conversion, use 16-bit grayscale if possible
                    if img.mode in ['I;16', 'I;16B']:
                        pass
                    else:
                        img = img.convert('I;16')  # 16-bit grayscale
                # Determine save params based on format
                save_kwargs = {}
                ext = options['format'].lower()
                if options['format'] == 'JPEG':
                    save_kwargs['quality'] = options['quality']
                    save_kwargs['optimize'] = True
                elif options['format'] == 'WEBP':
                    save_kwargs['quality'] = options['quality']
                    save_kwargs['method'] = 6
                # Build new filename with extension
                base = os.path.splitext(filename)[0]
                new_filename = f"{base}_compressed.{ext}"
                new_filepath = os.path.join(IMAGES_DIR, new_filename)
                img.save(new_filepath, format=options['format'], **save_kwargs)

                # Update DB entry to new file and remove old file
                if filepath != new_filepath:
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass
                    self.db.update_image_path(image_id, new_filepath)

            except Exception as e:
                QMessageBox.warning(self, "Compression Error", f"Failed to compress {filename}:\n{e}")

        self.model.refresh()
        QMessageBox.information(self, "Compression Complete", f"Completed compressing {total} image(s).")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()