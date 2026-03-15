from setuptools import setup, find_packages

setup(
    name="gesture-automation",
    version="1.0.0",
    description="Gesture-based home automation with OpenCV, MediaPipe & PyFirmata",
    author="Roy Carlous C",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=["opencv-python>=4.8.0", "mediapipe>=0.10.0", "numpy>=1.24.0"],
    extras_require={"hardware": ["pyfirmata>=1.1.0"], "dev": ["pytest>=7.0.0"]},
)
