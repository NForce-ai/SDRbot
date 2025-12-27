"""Utilities for handling image paste from clipboard.

Supports clipboard image reading on:
- macOS: via Pillow's ImageGrab or osascript fallback
- Windows: via Pillow's ImageGrab
- Linux: via xclip (requires: sudo apt install xclip)

Adapted from upstream deepagents-cli with cross-platform improvements.
"""

from __future__ import annotations

import base64
import io
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field


@dataclass
class ImageData:
    """Represents a pasted image with its base64 encoding."""

    base64_data: str
    format: str = "png"  # "png", "jpeg", etc.
    placeholder: str = field(default="[image]")

    def to_message_content(self) -> dict:
        """Convert to LangChain message content format.

        Returns:
            Dict with type and image_url for multimodal messages
        """
        return {
            "type": "image_url",
            "image_url": {"url": f"data:image/{self.format};base64,{self.base64_data}"},
        }


class ImageTracker:
    """Track pasted images for the current message."""

    def __init__(self) -> None:
        self.images: list[ImageData] = []
        self._next_id = 1

    def add_image(self, image_data: ImageData) -> str:
        """Add an image and return its placeholder text.

        Args:
            image_data: The image data to track

        Returns:
            Placeholder string like "[image 1]"
        """
        placeholder = f"[image {self._next_id}]"
        image_data.placeholder = placeholder
        self.images.append(image_data)
        self._next_id += 1
        return placeholder

    def get_images(self) -> list[ImageData]:
        """Get all tracked images."""
        return self.images.copy()

    def clear(self) -> None:
        """Clear all tracked images and reset counter."""
        self.images.clear()
        self._next_id = 1

    def has_images(self) -> bool:
        """Check if there are any tracked images."""
        return len(self.images) > 0


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


def _normalize_path(text: str) -> str:
    """Normalize a path, handling file:// URIs and extra whitespace.

    Args:
        text: Raw text that might be a path

    Returns:
        Normalized path string
    """
    text = text.strip()
    # Handle file:// URI (common when copying from file managers)
    if text.startswith("file://"):
        from urllib.parse import unquote, urlparse

        parsed = urlparse(text)
        text = unquote(parsed.path)
    return text


def load_image_from_path(path: str) -> ImageData | None:
    """Load an image from a file path.

    Args:
        path: Path to the image file (can be file:// URI)

    Returns:
        ImageData if successfully loaded, None otherwise
    """
    path = _normalize_path(path)
    if not os.path.isfile(path):
        return None

    # Check extension
    ext = os.path.splitext(path)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        return None

    try:
        from PIL import Image

        with Image.open(path) as img:
            # Convert to PNG for consistency
            buffer = io.BytesIO()
            # Convert to RGB if necessary (e.g., for RGBA or palette images)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGBA")
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.save(buffer, format="PNG")
            buffer.seek(0)
            base64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return ImageData(base64_data=base64_data, format="png")
    except Exception:
        return None


def is_image_path(text: str) -> bool:
    """Check if text looks like an image file path.

    Args:
        text: Text to check

    Returns:
        True if text appears to be an image file path
    """
    text = _normalize_path(text)
    if not text:
        return False
    # Check if it's a path with an image extension
    ext = os.path.splitext(text)[1].lower()
    return ext in IMAGE_EXTENSIONS


def get_clipboard_image() -> ImageData | None:
    """Attempt to read an image from the system clipboard.

    Returns:
        ImageData if an image is found, None otherwise
    """
    # Try Pillow's ImageGrab first (works on Windows and macOS)
    try:
        from PIL import ImageGrab

        img = ImageGrab.grabclipboard()
        if img is not None:
            # Convert to PNG bytes
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            base64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return ImageData(base64_data=base64_data, format="png")
    except Exception:
        pass

    # Platform-specific fallbacks
    if sys.platform == "darwin":
        return _get_macos_clipboard_image()
    elif sys.platform == "linux":
        return _get_linux_clipboard_image()

    return None


def _get_macos_clipboard_image() -> ImageData | None:
    """Get clipboard image on macOS using osascript.

    Returns:
        ImageData if an image is found, None otherwise
    """
    # Create a temp file for the image
    fd, temp_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)

    try:
        # First check if clipboard has image data
        check_result = subprocess.run(
            ["osascript", "-e", "clipboard info"],
            capture_output=True,
            check=False,
            timeout=2,
            text=True,
        )

        if check_result.returncode != 0:
            return None

        clipboard_info = check_result.stdout.lower()
        if "pngf" not in clipboard_info and "tiff" not in clipboard_info:
            return None

        # Get the image data
        if "pngf" in clipboard_info:
            get_script = f"""
            set pngData to the clipboard as «class PNGf»
            set theFile to open for access POSIX file "{temp_path}" with write permission
            write pngData to theFile
            close access theFile
            return "success"
            """
        else:
            get_script = f"""
            set tiffData to the clipboard as TIFF picture
            set theFile to open for access POSIX file "{temp_path}" with write permission
            write tiffData to theFile
            close access theFile
            return "success"
            """

        result = subprocess.run(
            ["osascript", "-e", get_script],
            capture_output=True,
            check=False,
            timeout=3,
            text=True,
        )

        if result.returncode != 0 or "success" not in result.stdout:
            return None

        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            return None

        # Read and convert to PNG
        with open(temp_path, "rb") as f:
            image_data = f.read()

        try:
            from PIL import Image

            image = Image.open(io.BytesIO(image_data))
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)
            base64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return ImageData(base64_data=base64_data, format="png")
        except Exception:
            return None

    except (subprocess.TimeoutExpired, OSError):
        return None
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def _get_linux_clipboard_image() -> ImageData | None:
    """Get clipboard image on Linux using xclip.

    Requires: sudo apt install xclip

    Returns:
        ImageData if an image is found, None otherwise
    """
    try:
        # Try to get PNG from clipboard
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
            capture_output=True,
            check=False,
            timeout=2,
        )

        if result.returncode == 0 and result.stdout:
            # Validate it's a real image
            try:
                from PIL import Image

                Image.open(io.BytesIO(result.stdout))
                base64_data = base64.b64encode(result.stdout).decode("utf-8")
                return ImageData(base64_data=base64_data, format="png")
            except Exception:
                pass

    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def create_multimodal_content(text: str, images: list[ImageData]) -> list[dict]:
    """Create multimodal message content with text and images.

    Args:
        text: Text content of the message
        images: List of ImageData objects

    Returns:
        List of content blocks in LangChain format
    """
    content_blocks = []

    # Add text block first
    if text.strip():
        content_blocks.append({"type": "text", "text": text})

    # Add image blocks
    for image in images:
        content_blocks.append(image.to_message_content())

    return content_blocks


__all__ = [
    "ImageData",
    "ImageTracker",
    "get_clipboard_image",
    "load_image_from_path",
    "is_image_path",
    "create_multimodal_content",
]
