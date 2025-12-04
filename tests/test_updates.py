"""Tests for update checking functionality."""

from unittest.mock import patch

from sdrbot_cli.updates import GITHUB_REPO, check_for_updates


class TestCheckForUpdates:
    """Tests for check_for_updates function."""

    def test_test_mode_returns_fake_version(self, monkeypatch):
        """Test mode via env var returns fake version."""
        monkeypatch.setenv("SDRBOT_TEST_UPDATE", "2.0.0")

        version, url = check_for_updates()

        assert version == "2.0.0"
        assert url == f"https://github.com/{GITHUB_REPO}/releases/tag/v2.0.0"

    def test_test_mode_not_set_does_real_check(self, monkeypatch):
        """Without test env var, does real GitHub check."""
        monkeypatch.delenv("SDRBOT_TEST_UPDATE", raising=False)

        with patch("sdrbot_cli.updates.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "tag_name": "v0.0.1",  # Older than current
                "html_url": "https://github.com/test/releases/v0.0.1",
            }

            version, url = check_for_updates()

            mock_get.assert_called_once()
            assert version is None
            assert url is None

    def test_newer_version_available(self, monkeypatch):
        """Returns version info when newer version exists."""
        monkeypatch.delenv("SDRBOT_TEST_UPDATE", raising=False)

        with patch("sdrbot_cli.updates.requests.get") as mock_get:
            with patch("sdrbot_cli.updates.__version__", "0.1.0"):
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = {
                    "tag_name": "v1.0.0",
                    "html_url": "https://github.com/test/releases/v1.0.0",
                }

                version, url = check_for_updates()

                assert version == "1.0.0"
                assert url == "https://github.com/test/releases/v1.0.0"

    def test_same_version_returns_none(self, monkeypatch):
        """Returns None when current version matches latest."""
        monkeypatch.delenv("SDRBOT_TEST_UPDATE", raising=False)

        with patch("sdrbot_cli.updates.requests.get") as mock_get:
            with patch("sdrbot_cli.updates.__version__", "1.0.0"):
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = {
                    "tag_name": "v1.0.0",
                    "html_url": "https://github.com/test/releases/v1.0.0",
                }

                version, url = check_for_updates()

                assert version is None
                assert url is None

    def test_older_version_on_github_returns_none(self, monkeypatch):
        """Returns None when GitHub version is older (edge case)."""
        monkeypatch.delenv("SDRBOT_TEST_UPDATE", raising=False)

        with patch("sdrbot_cli.updates.requests.get") as mock_get:
            with patch("sdrbot_cli.updates.__version__", "2.0.0"):
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = {
                    "tag_name": "v1.0.0",
                    "html_url": "https://github.com/test/releases/v1.0.0",
                }

                version, url = check_for_updates()

                assert version is None
                assert url is None

    def test_network_error_returns_none(self, monkeypatch):
        """Returns None on network error."""
        monkeypatch.delenv("SDRBOT_TEST_UPDATE", raising=False)

        with patch("sdrbot_cli.updates.requests.get") as mock_get:
            mock_get.side_effect = Exception("Network error")

            version, url = check_for_updates()

            assert version is None
            assert url is None

    def test_non_200_status_returns_none(self, monkeypatch):
        """Returns None on non-200 HTTP status."""
        monkeypatch.delenv("SDRBOT_TEST_UPDATE", raising=False)

        with patch("sdrbot_cli.updates.requests.get") as mock_get:
            mock_get.return_value.status_code = 404

            version, url = check_for_updates()

            assert version is None
            assert url is None

    def test_missing_tag_name_returns_none(self, monkeypatch):
        """Returns None when response lacks tag_name."""
        monkeypatch.delenv("SDRBOT_TEST_UPDATE", raising=False)

        with patch("sdrbot_cli.updates.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "html_url": "https://github.com/test/releases/latest",
            }

            version, url = check_for_updates()

            assert version is None
            assert url is None

    def test_tag_name_without_v_prefix(self, monkeypatch):
        """Handles tag names without 'v' prefix."""
        monkeypatch.delenv("SDRBOT_TEST_UPDATE", raising=False)

        with patch("sdrbot_cli.updates.requests.get") as mock_get:
            with patch("sdrbot_cli.updates.__version__", "0.1.0"):
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = {
                    "tag_name": "1.0.0",  # No 'v' prefix
                    "html_url": "https://github.com/test/releases/1.0.0",
                }

                version, url = check_for_updates()

                assert version == "1.0.0"
                assert url == "https://github.com/test/releases/1.0.0"

    def test_request_timeout(self, monkeypatch):
        """Verifies request uses timeout."""
        monkeypatch.delenv("SDRBOT_TEST_UPDATE", raising=False)

        with patch("sdrbot_cli.updates.requests.get") as mock_get:
            mock_get.return_value.status_code = 404

            check_for_updates()

            # Verify timeout was passed
            mock_get.assert_called_once()
            call_kwargs = mock_get.call_args[1]
            assert "timeout" in call_kwargs
            assert call_kwargs["timeout"] == 2
