"""Local English-to-Hindi translation. Source text never leaves this process."""
from functools import lru_cache
from threading import Lock

from app import config  # sets Argos data directories before its first import


_install_lock = Lock()
ENGINE = "argos-en-hi"


@lru_cache(maxsize=1)
def _translator():
    import argostranslate.package as packages
    import argostranslate.translate as translate

    with _install_lock:
        languages = translate.get_installed_languages()
        english = next((language for language in languages if language.code == "en"), None)
        hindi = next((language for language in languages if language.code == "hi"), None)
        if english is None or hindi is None:
            packages.update_package_index()
            available = packages.get_available_packages()
            package = next((item for item in available if item.from_code == "en" and item.to_code == "hi"), None)
            if package is None:
                raise RuntimeError("English-to-Hindi model is absent from the Argos package index")
            packages.install_from_path(package.download())
            languages = translate.get_installed_languages()
            english = next((language for language in languages if language.code == "en"), None)
            hindi = next((language for language in languages if language.code == "hi"), None)
        if english is None or hindi is None:
            raise RuntimeError("English-to-Hindi model installation did not complete")
        return english.get_translation(hindi)


def translate_text(text: str) -> str:
    source = text.strip()
    if not source:
        raise ValueError("Text is empty")
    if len(source) > 5000:
        raise ValueError("Translate at most 5000 characters at once")
    result = _translator().translate(source).strip()
    if not result:
        raise RuntimeError("Translation model returned no text")
    return result
