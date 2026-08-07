import pytest

from app.core.config import Settings
from app.core.exceptions import InvalidRequestError
from app.services.uploads_service import _extract_text, _validate_upload


def _settings(**overrides) -> Settings:
    return Settings(**overrides)


class TestValidateUpload:
    def test_accepts_an_allowed_extension_within_the_size_limit(self) -> None:
        extension = _validate_upload("notes.txt", size_bytes=100, settings=_settings())
        assert extension == ".txt"

    def test_rejects_a_disallowed_extension(self) -> None:
        with pytest.raises(InvalidRequestError, match="Unsupported file type"):
            _validate_upload("script.exe", size_bytes=100, settings=_settings())

    def test_rejects_a_file_over_the_size_limit(self) -> None:
        settings = _settings(max_upload_bytes=1000)
        with pytest.raises(InvalidRequestError, match="too large"):
            _validate_upload("notes.txt", size_bytes=1001, settings=settings)

    def test_extension_matching_is_case_insensitive(self) -> None:
        extension = _validate_upload("REPORT.PDF", size_bytes=100, settings=_settings())
        assert extension == ".pdf"


class TestExtractText:
    def test_decodes_plain_text_files(self) -> None:
        assert _extract_text(b"hello world", ".txt") == "hello world"

    def test_decodes_markdown_and_csv_the_same_way_as_text(self) -> None:
        assert _extract_text(b"# heading", ".md") == "# heading"
        assert _extract_text(b"a,b,c\n1,2,3", ".csv") == "a,b,c\n1,2,3"

    def test_leniently_replaces_undecodable_bytes_instead_of_raising(self) -> None:
        invalid_utf8 = b"valid text \xff\xfe more text"
        result = _extract_text(invalid_utf8, ".txt")
        assert "valid text" in result
        assert "more text" in result

    def test_a_malformed_pdf_returns_empty_text_instead_of_raising(self) -> None:
        assert _extract_text(b"this is not a real pdf", ".pdf") == ""
