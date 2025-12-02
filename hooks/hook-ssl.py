"""Runtime hook to configure SSL certificates for bundled executables.

This ensures requests/urllib3 can find the certifi CA bundle when running
as a PyInstaller-bundled executable on macOS and Windows.
"""

import os
import sys


def _configure_ssl():
    """Set SSL_CERT_FILE to the bundled certifi CA bundle."""
    # Only configure if running as a bundled executable
    if not getattr(sys, "frozen", False):
        return

    # Try to find certifi's cacert.pem in the bundle
    try:
        import certifi

        ca_bundle = certifi.where()
        if os.path.exists(ca_bundle):
            os.environ["SSL_CERT_FILE"] = ca_bundle
            os.environ["REQUESTS_CA_BUNDLE"] = ca_bundle
    except ImportError:
        pass


_configure_ssl()
