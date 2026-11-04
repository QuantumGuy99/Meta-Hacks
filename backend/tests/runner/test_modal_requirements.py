"""requirements.txt → image packages for ModalRunner (no Modal needed)."""

import pytest

from crucible.runner.base import RunnerError
from crucible.runner.modal_runner import parse_requirements


def test_pinned_and_bare_packages_are_accepted_sorted_and_deduplicated():
    text = "# deps\nuvicorn==0.32.1\nfastapi==0.115.6\n\nhttpx  # client\nfastapi==0.115.6\nuvicorn[standard]>=0.30\n"
    assert parse_requirements(text) == (
        "fastapi==0.115.6",
        "httpx",
        "uvicorn==0.32.1",
        "uvicorn[standard]>=0.30",
    )


@pytest.mark.parametrize(
    "line",
    [
        "-r other.txt",
        "--index-url https://evil.example",
        "git+https://x/y.git",
        "pkg; rm -rf /",
        "./local",
        "a @ b",
    ],
)
def test_anything_but_a_package_name_is_rejected(line):
    with pytest.raises(RunnerError, match="can't install"):
        parse_requirements(line)


def test_too_many_requirements_are_rejected():
    with pytest.raises(RunnerError, match="limit"):
        parse_requirements("\n".join(f"pkg{i}" for i in range(30)))


def test_empty_requirements_mean_the_base_image():
    assert parse_requirements("") == ()
