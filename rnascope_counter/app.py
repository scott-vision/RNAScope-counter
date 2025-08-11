import csv
import sys
from typing import Dict, List, Tuple

import numpy as np
from PyQt6.QtCore import QPoint, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QMainWindow,
    QRubberBand,
)
from skimage.feature import peak_local_max
import tifffile


def load_image(path: str) -> np.ndarray:
    """Load a TIFF image and return channels as (C, H, W) array."""
    data = tifffile.imread(path)
    if data.ndim == 4:
        # assume (z, c, y, x)
        data = data.max(axis=0)
    if data.ndim == 3 and data.shape[0] == 3:
        return data
    if data.ndim == 3 and data.shape[-1] == 3:
        return np.moveaxis(data, -1, 0)
    raise ValueError("Expected 3-channel image")


def array_to_pixmap(arr: np.ndarray) -> QPixmap:
    arr = arr.astype(float)
    arr -= arr.min()
    if arr.max() > 0:
        arr /= arr.max()
    arr = (arr * 255).astype(np.uint8)
    h, w = arr.shape
    image = QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8)
    return QPixmap.fromImage(image)


class ROIImageLabel(QLabel):
    roiSelected = pyqtSignal(QRect)

    def __init__(self, array: np.ndarray, parent=None):
        super().__init__(parent)
        self.setPixmap(array_to_pixmap(array))
        self._rubber = QRubberBand(QRubberBand.Rectangle, self)
        self._origin = QPoint()

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


def analyze(channel: np.ndarray, rect: QRect, threshold: float = 100) -> Tuple[int, float, float]:
    x, y, w, h = rect.left(), rect.top(), rect.width(), rect.height()
    sub = channel[y : y + h, x : x + w]
    coords = peak_local_max(sub, min_distance=2, threshold_abs=threshold)
    intensities = sub[coords[:, 0], coords[:, 1]] if coords.size else np.array([])
    count = int(len(intensities))
    total = float(np.sum(intensities)) if count else 0.0
    avg = float(np.mean(intensities)) if count else 0.0
    return count, total, avg


class RNAScopeCounterApp(QMainWindow):
    def __init__(self, hippo_path: str, thal_path: str, output_path: str):
        super().__init__()
        self.hipp_channels = load_image(hippo_path)
        self.thal_channels = load_image(thal_path)
        self.output_path = output_path
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
                self.image_label.setPixmap(array_to_pixmap(self.thal_channels[0]))
                self.statusBar().showMessage("Select ROI for Thalamus")
            else:
                self.finish()

    def finish(self):
        results: List[List[object]] = []
        for region, rect in self.hipp_rois.items():
            for chan_name, chan_idx in [("GOB", 1), ("GOA", 2)]:
                count, total, avg = analyze(self.hipp_channels[chan_idx], rect)
                results.append([region, chan_name, count, total, avg])
        for region, rect in self.thal_rois.items():
            for chan_name, chan_idx in [("GOB", 1), ("GOA", 2)]:
                count, total, avg = analyze(self.thal_channels[chan_idx], rect)
                results.append([region, chan_name, count, total, avg])
        with open(self.output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Region", "Channel", "SpotCount", "TotalIntensity", "AverageIntensity"])
            writer.writerows(results)
        QMessageBox.information(self, "RNAScope Counter", f"Results saved to {self.output_path}")
        QApplication.quit()


def run_app(hippo_path: str, thal_path: str, output_path: str):
    app = QApplication(sys.argv)
    win = RNAScopeCounterApp(hippo_path, thal_path, output_path)
    win.show()
    app.exec()
