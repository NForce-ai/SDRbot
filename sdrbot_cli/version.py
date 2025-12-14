from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("sdrbot")
except PackageNotFoundError:
    # If the package is not installed (e.g. running from source without install),
    # fallback to the version defined in pyproject.toml
    __version__ = "0.1.0a3"
