import sys
import os
import subprocess
import threading
import json
import shutil
import glob
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QGroupBox,
    QRadioButton,
    QLabel,
    QTextEdit,
)
from PySide6.QtCore import Qt, Signal, QObject


class Communicate(QObject):
    log_message = Signal(str)
    processing_finished = Signal()


class DeflickerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("All-In-One Deflicker GUI")
        self.setGeometry(100, 100, 700, 500)

        self.comm = Communicate()
        self.comm.log_message.connect(self.log)
        self.comm.processing_finished.connect(self.on_processing_finished)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- Input Selection ---
        input_group = QGroupBox("Input")
        input_layout = QVBoxLayout(input_group)

        self.video_folder_radio = QRadioButton("Batch process video folder")
        self.frames_folder_radio = QRadioButton("Batch process frames folder")
        self.video_folder_radio.setChecked(True)

        # Video folder input
        self.video_folder_path = QLineEdit()
        self.video_browse_button = QPushButton("Browse")
        video_layout = QHBoxLayout()
        video_layout.addWidget(self.video_folder_path)
        video_layout.addWidget(self.video_browse_button)

        # Frames folder input
        self.frames_folder_path = QLineEdit()
        self.frames_browse_button = QPushButton("Browse")
        frames_layout = QHBoxLayout()
        frames_layout.addWidget(self.frames_folder_path)
        frames_layout.addWidget(self.frames_browse_button)

        input_layout.addWidget(self.video_folder_radio)
        input_layout.addLayout(video_layout)
        input_layout.addWidget(self.frames_folder_radio)
        input_layout.addLayout(frames_layout)

        # --- Output Selection ---
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)
        output_folder_layout = QHBoxLayout()
        self.output_folder_path = QLineEdit()
        self.output_browse_button = QPushButton("Browse")
        output_folder_layout.addWidget(QLabel("Output Folder:"))
        output_folder_layout.addWidget(self.output_folder_path)
        output_folder_layout.addWidget(self.output_browse_button)
        output_layout.addLayout(output_folder_layout)

        gpu_layout = QHBoxLayout()
        self.gpu_id_input = QLineEdit("0")
        self.gpu_id_input.setFixedWidth(50)
        gpu_layout.addWidget(QLabel("GPU ID:"))
        gpu_layout.addWidget(self.gpu_id_input)
        gpu_layout.addStretch()
        output_layout.addLayout(gpu_layout)

        self.process_button = QPushButton("Process")
        self.process_button.setStyleSheet("font-weight: bold; height: 30px;")

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFontFamily("Courier")

        main_layout.addWidget(input_group)
        main_layout.addWidget(output_group)
        main_layout.addWidget(self.process_button)
        main_layout.addWidget(QLabel("Log:"))
        main_layout.addWidget(self.log_area)

        self.video_folder_radio.toggled.connect(self.toggle_input_mode)
        self.video_browse_button.clicked.connect(self.browse_video_folder)
        self.frames_browse_button.clicked.connect(self.browse_frames_folder)
        self.output_browse_button.clicked.connect(self.browse_output_folder)
        self.process_button.clicked.connect(self.start_processing_thread)

        self.toggle_input_mode()

    def toggle_input_mode(self):
        is_video_mode = self.video_folder_radio.isChecked()
        self.video_folder_path.setEnabled(is_video_mode)
        self.video_browse_button.setEnabled(is_video_mode)
        self.frames_folder_path.setEnabled(not is_video_mode)
        self.frames_browse_button.setEnabled(not is_video_mode)

    def browse_video_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Video Folder")
        if folder:
            self.video_folder_path.setText(folder)

    def browse_frames_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Frames Folder")
        if folder:
            self.frames_folder_path.setText(folder)

    def browse_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder_path.setText(folder)

    def log(self, message):
        self.log_area.append(message)
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())
        QApplication.processEvents()

    def on_processing_finished(self):
        self.process_button.setEnabled(True)
        self.log("---------------------\nAll processing finished.")

    def start_processing_thread(self):
        self.process_button.setEnabled(False)
        self.log_area.clear()
        thread = threading.Thread(target=self.process_controller)
        thread.daemon = True
        thread.start()

    def get_video_fps(self, video_path):
        try:
            cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "json", video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            data = json.loads(result.stdout)
            rate = data["streams"][0]["r_frame_rate"]
            num, den = map(int, rate.split('/'))
            return num / den
        except Exception as e:
            self.comm.log_message.emit(f"Error getting FPS for {os.path.basename(video_path)}: {e}")
            return None

    def run_command(self, cmd):
        self.comm.log_message.emit(f"\n> {' '.join(cmd)}")
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in process.stdout:
                self.comm.log_message.emit(line.strip())
            process.wait()
            if process.returncode != 0:
                self.comm.log_message.emit(f"--- Command failed with exit code {process.returncode} ---")
            return process.returncode
        except FileNotFoundError:
            self.comm.log_message.emit(f"--- Command not found: {cmd[0]}. Please ensure it is installed and in your system's PATH. ---")
            return -1

    def process_controller(self):
        output_folder = self.output_folder_path.text()
        if not output_folder:
            self.comm.log_message.emit("Error: Output folder not selected.")
            self.comm.processing_finished.emit()
            return

        os.makedirs(output_folder, exist_ok=True)
        os.makedirs("./data/test", exist_ok=True)
        os.makedirs("./results", exist_ok=True)

        if self.video_folder_radio.isChecked():
            self.process_video_folder(self.video_folder_path.text(), output_folder)
        else:
            self.process_frames_folder(self.frames_folder_path.text(), output_folder)

        self.comm.processing_finished.emit()

    def process_video_folder(self, input_folder, output_folder):
        if not input_folder:
            self.comm.log_message.emit("Error: Video folder not selected.")
            return

        self.comm.log_message.emit(f"Starting batch processing for video folder: {input_folder}")
        videos = [f for f in os.listdir(input_folder) if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))]
        if not videos:
            self.comm.log_message.emit("No video files found in the selected folder.")
            return

        for video_file in videos:
            self.process_single_item(video_file, input_folder, output_folder)

    def process_frames_folder(self, input_folder, output_folder):
        if not input_folder:
            self.comm.log_message.emit("Error: Frames folder not selected.")
            return
        self.comm.log_message.emit(f"Starting processing for frames folder: {input_folder}")
        self.process_single_item(os.path.basename(input_folder), os.path.dirname(input_folder), output_folder, is_frames=True)

    def process_single_item(self, item_name, root_folder, output_folder, is_frames=False):
        self.comm.log_message.emit(f"\n---------------------\nProcessing: {item_name}")
        
        video_base_name = os.path.splitext(item_name)[0] if not is_frames else item_name
        temp_frames_dir = os.path.abspath(os.path.join("./data/test", video_base_name))
        temp_results_dir = os.path.abspath(os.path.join("./results", video_base_name))
        
        fps = None

        # --- Step 1: Prepare Frames ---
        if is_frames:
            source_frames_dir = os.path.join(root_folder, item_name)
            self.comm.log_message.emit(f"Copying frames from {source_frames_dir} to {temp_frames_dir}")
            try:
                if os.path.exists(temp_frames_dir):
                    shutil.rmtree(temp_frames_dir)
                shutil.copytree(source_frames_dir, temp_frames_dir)
            except Exception as e:
                self.comm.log_message.emit(f"Error copying frames: {e}")
                return
        else:
            video_path = os.path.join(root_folder, item_name)
            fps = self.get_video_fps(video_path)
            if fps is None:
                return
            os.makedirs(temp_frames_dir, exist_ok=True)
            cmd = ["ffmpeg", "-i", video_path, "-vf", f"fps={fps}", "-start_number", "0", os.path.join(temp_frames_dir, "%05d.png")]
            if self.run_command(cmd) != 0:
                self.cleanup([temp_frames_dir])
                return

        gpu_id = self.gpu_id_input.text()

        # --- Step 2: Run Processing Scripts ---
        cmd_atlas = ["python", "src/stage1_neural_atlas.py", "--vid_name", video_base_name, "--gpu", gpu_id]
        if self.run_command(cmd_atlas) != 0:
            self.cleanup([temp_frames_dir])
            return
        
        # For frame processing, the script still needs an FPS to generate the intermediate video. Use a default of 30.
        effective_fps = fps if not is_frames else 30
        cmd_refine = ["python", "src/neural_filter_and_refinement.py", "--video_name", video_base_name, "--fps", str(effective_fps), "--gpu", gpu_id]
        
        if self.run_command(cmd_refine) != 0:
            self.cleanup([temp_frames_dir, temp_results_dir])
            return

        # --- Step 3: Handle Result ---
        if is_frames:
            # The script creates an intermediate video. We extract frames from it.
            result_videos = glob.glob(os.path.join(temp_results_dir, "**", "*.mp4"), recursive=True)
            if result_videos:
                intermediate_video_path = result_videos[0]
                final_output_dir = os.path.join(output_folder, f"{video_base_name}_refined_frames")
                os.makedirs(final_output_dir, exist_ok=True)
                self.comm.log_message.emit(f"\nExtracting and converting frames from intermediate video to: {final_output_dir}")

                output_pattern = os.path.join(final_output_dir, "%08d.png")
                convert_cmd = ["ffmpeg", "-i", intermediate_video_path, "-pix_fmt", "gray16be", "-y", output_pattern]
                
                self.run_command(convert_cmd)
                self.comm.log_message.emit("Frame extraction and conversion complete.")
            else:
                self.comm.log_message.emit(f"\n--- Could not find intermediate video in {temp_results_dir} ---")
        else: # Video output
            result_videos = glob.glob(os.path.join(temp_results_dir, "**", "*.mp4"), recursive=True)
            if result_videos:
                result_video_path = result_videos[0]
                final_name = f"{video_base_name}_refined.mp4"
                final_output_path = os.path.join(output_folder, final_name)
                self.comm.log_message.emit(f"\nMoving result to: {final_output_path}")
                shutil.move(result_video_path, final_output_path)
            else:
                self.comm.log_message.emit(f"\n--- Could not find processed video in {temp_results_dir} ---")

        # --- Step 4: Cleanup ---
        self.cleanup([temp_frames_dir, temp_results_dir])
        self.comm.log_message.emit(f"Finished processing {item_name}.")

    def cleanup(self, dirs_to_remove):
        self.comm.log_message.emit("\nCleaning up temporary files...")
        for d in dirs_to_remove:
            if os.path.exists(d):
                try:
                    shutil.rmtree(d)
                    self.comm.log_message.emit(f"Removed: {d}")
                except Exception as e:
                    self.comm.log_message.emit(f"Error removing {d}: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DeflickerGUI()
    window.show()
    sys.exit(app.exec())
