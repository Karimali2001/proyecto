# Copilot Instructions for AI Agents

## Project Overview
This project is an object detection system designed for embedded Linux devices (e.g., Raspberry Pi) using the Hailo AI accelerator and Picamera2. It integrates camera input, object detection, and audio feedback for accessibility or navigation assistance.

# Coding Standards and Language

Language: All code must be written in English. This includes:

Variable names, function names, class names, and constants.

All logs and console output (unless they are part of the user-facing translation).

Commenting: Every significant function, class, and complex logic block must include comments in English.

Use clear, concise docstrings for functions.

Explain "why" something is being done, especially in hardware-interfacing code.

Consistency: Do not mix languages in the codebase.

## Architecture & Key Components
- **main.py**: Entry point. Launches threads for object detection, audio output, and ToF sensor-based hole detection. Uses a queue for cross-thread communication.
- **src/core/**: Contains core logic (e.g., object_inference.py for running inference).
- **src/drivers/**: Hardware abstraction layer. Includes drivers for Hailo, camera, ToF, IMU, GPS, Raspberry Pi, and audio/button interfaces.
  - Example: `HailoDriver` wraps Hailo device, handles model loading, inference, and detection parsing.
  - Example: `CameraDriver` wraps Picamera2, manages configuration and frame capture.
- **src/ui/**: User interface components (console logger, voice interface).
- **assets/**: Models, label files, translations, and config files.

## Developer Workflows
- **System Setup**: Install required system packages (see README.md).
- **Python Environment**: Use a virtual environment with `--system-site-packages` to access Picamera2.
- **Dependency Management**: Install Python dependencies via `requirements.txt`. NumPy <2.0 and OpenCV-headless are required.
- **Running Inference**: Use `python src/core/object_inference.py --model assets/yolov8s.hef --labels assets/coco.txt` from project root.
- **Debugging**: Most errors are logged to console. Use `Ctrl+C` to stop execution.

## Patterns & Conventions
- **Threading**: Main logic runs in separate threads for camera, audio, and ToF detection. Communication via a shared queue (`detectionsQueue`).
- **Model/Label Paths**: Paths are set in main.py and passed to drivers. Use assets directory for models and labels.
- **Translations**: Object names are translated using `translations.json`.
- **Error Handling**: Hardware initialization errors are caught and logged; execution continues where possible.
- **Driver Abstraction**: Each hardware component has a dedicated driver class in `src/drivers/`.

## Integration Points
- **Hailo AI Accelerator**: Integrated via `picamera2.devices.Hailo` in `HailoDriver`.
- **Picamera2**: Used for camera input in `CameraDriver`.
- **ToF Sensor**: Used for hole detection in `TofDriver`.
- **Audio Output**: Simulated via console print; real audio output can be implemented in `audio_output_driver.py`.

## Examples
- To add a new sensor, create a driver in `src/drivers/` and integrate it in `main.py` as a new thread.
- To change the model, update the model path in `main.py` or pass via command line to `object_inference.py`.

## References
- See `README.md` for setup and execution instructions.
- Key files: `main.py`, `src/drivers/hailo_driver.py`, `src/drivers/camera_driver.py`, `src/core/object_inference.py`, `assets/`.

---

**Review and update this file as the project evolves.**
