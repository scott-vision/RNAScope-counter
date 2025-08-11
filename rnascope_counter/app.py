import csv
import sys
from typing import Dict, List, Tuple

import numpy as np
from PyQt6.QtCore import QPoint, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QMessageBox,
    QMainWindow,
    QRubberBand,
    QInputDialog,
    QWidget,
)
from skimage.feature import peak_local_max
import tifffile


def load_image(path: str, already_max_projected: bool = False) -> np.ndarray:
    """Load a TIFF image and return channels as (C, H, W) array."""
    data = tifffile.imread(path)
    if data.ndim == 4:
        if already_max_projected:
            raise ValueError(
                "Image flagged as already max-projected but still has a z dimension"
            )
        # assume (z, c, y, x)
        data = data.max(axis=0)
    if data.ndim == 3 and data.shape[0] == 3:
        return data
    if data.ndim == 3 and data.shape[-1] == 3:
        return np.moveaxis(data, -1, 0)
    raise ValueError("Expected 3-channel image")


def array_to_qimage(arr: np.ndarray) -> QImage:
    """Convert a 2D array to a grayscale QImage.

    QPixmap on Windows relies on the GDI API which cannot handle images
    larger than 32767 pixels in either dimension (CreateDIBSection fails).
    Returning a QImage allows us to paint the image without that limitation.
    """
    arr = arr.astype(float)
    arr -= arr.min()
    if arr.max() > 0:
        arr /= arr.max()
    arr = (arr * 255).astype(np.uint8)
    h, w = arr.shape
    image = QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8)
    # copy to detach from numpy memory
    return image.copy()


class ROIImageLabel(QWidget):
    roiSelected = pyqtSignal(QRect)

    def __init__(self, array: np.ndarray, parent=None):
        super().__init__(parent)
        self._image = array_to_qimage(array)
        self.setFixedSize(self._image.size())
        band_shape = getattr(QRubberBand, "Shape", QRubberBand)
        self._rubber = QRubberBand(band_shape.Rectangle, self)
        self._origin = QPoint()

    def set_array(self, array: np.ndarray):
        self._image = array_to_qimage(array)
        self.setFixedSize(self._image.size())
        self.update()

    def paintEvent(self, event):  # type: ignore[override]
        painter = QPainter(self)
        painter.drawImage(0, 0, self._image)

    def mousePressEvent(self, event):  # type: ignore[override]
        self._origin = event.position().toPoint()
        self._rubber.setGeometry(QRect(self._origin, QSize()))
        self._rubber.show()

    def mouseMoveEvent(self, event):  # type: ignore[override]
        self._rubber.setGeometry(QRect(self._origin, event.position().toPoint()).normalized())

    def mouseReleaseEvent(self, event):  # type: ignore[override]
        self._rubber.hide()
        rect = self._rubber.geometry()
        self.roiSelected.emit(rect)


def analyze(
    channel: np.ndarray, rect: QRect, pixel_spacing: float, threshold: float = 100
) -> Tuple[int, float, float, float]:
    x, y, w, h = rect.left(), rect.top(), rect.width(), rect.height()
    sub = channel[y : y + h, x : x + w]
    coords = peak_local_max(sub, min_distance=2, threshold_abs=threshold)
    intensities = sub[coords[:, 0], coords[:, 1]] if coords.size else np.array([])
    count = int(len(intensities))
    total = float(np.sum(intensities)) if count else 0.0
    avg = float(np.mean(intensities)) if count else 0.0
    area_sq_micron = (w * pixel_spacing) * (h * pixel_spacing)
    density = count / area_sq_micron if area_sq_micron > 0 else 0.0
    return count, total, avg, density


class RNAScopeCounterApp(QMainWindow):
    def __init__(
        self,
        hippo_path: str,
        thal_path: str,
        output_path: str,
        pixel_spacing: float,
        max_projected: bool,
    ):
        super().__init__()
        self.hipp_channels = load_image(hippo_path, already_max_projected=max_projected)
        self.thal_channels = load_image(thal_path, already_max_projected=max_projected)
        self.output_path = output_path
        self.pixel_spacing = pixel_spacing
        self.hipp_rois: Dict[str, QRect] = {}
        self.thal_rois: Dict[str, QRect] = {}

        self.image_label = ROIImageLabel(self.hipp_channels[0])
        self.image_label.roiSelected.connect(self._roi_complete)
        self.setCentralWidget(self.image_label)

        self.current_image = "hippocampus"
        self.expected_rois: List[str] = ["CA1", "CA3", "DG"]
        self.current_roi_index = 0
        self.statusBar().showMessage(f"Select ROI for {self.expected_rois[0]}")
        self.setWindowTitle("RNAScope Counter")

    def _roi_complete(self, rect: QRect):
        region = self.expected_rois[self.current_roi_index]
        if self.current_image == "hippocampus":
            self.hipp_rois[region] = rect
        else:
            self.thal_rois[region] = rect
        self.current_roi_index += 1
        if self.current_roi_index < len(self.expected_rois):
            next_region = self.expected_rois[self.current_roi_index]
            self.statusBar().showMessage(f"Select ROI for {next_region}")
        else:
            if self.current_image == "hippocampus":
                self.current_image = "thalamus"
                self.expected_rois = ["Thalamus"]
                self.current_roi_index = 0
                self.image_label.set_array(self.thal_channels[0])
                self.statusBar().showMessage("Select ROI for Thalamus")
            else:
                self.finish()

    def finish(self):
        results: List[List[object]] = []
        for region, rect in self.hipp_rois.items():
            for chan_name, chan_idx in [("GOB", 1), ("GOA", 2)]:
                count, total, avg, density = analyze(
                    self.hipp_channels[chan_idx], rect, self.pixel_spacing
                )
                results.append([region, chan_name, count, total, avg, density])
        for region, rect in self.thal_rois.items():
            for chan_name, chan_idx in [("GOB", 1), ("GOA", 2)]:
                count, total, avg, density = analyze(
                    self.thal_channels[chan_idx], rect, self.pixel_spacing
                )
                results.append([region, chan_name, count, total, avg, density])
        with open(self.output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Region",
                    "Channel",
                    "SpotCount",
                    "TotalIntensity",
                    "AverageIntensity",
                    "SpotsPerSquareMicron",
                ]
            )
            writer.writerows(results)
        QMessageBox.information(self, "RNAScope Counter", f"Results saved to {self.output_path}")
        QApplication.quit()


def run_app(
    hippo_path: str, thal_path: str, output_path: str, max_projected: bool = False
):
    app = QApplication(sys.argv)
    pixel_spacing, ok = QInputDialog.getDouble(
        None, "Pixel Spacing", "Microns per pixel:", 0.4475, 0, 1e6, 4
    )
    if not ok:
        pixel_spacing = 0.4475
    win = RNAScopeCounterApp(
        hippo_path, thal_path, output_path, pixel_spacing, max_projected
    )
    win.show()
    app.exec()
