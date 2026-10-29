import pytest
from jarvis.applications import resolve_application


def test_missing_word_uses_existing_pages():
    apps = [{"name": "Pages", "path": "/Applications/Pages Creator Studio.app"}, {"name": "TextEdit", "path": "/System/Applications/TextEdit.app"}]
    result = resolve_application("Word", apps)
    assert result["name"] == "Pages"
    assert result["fallback"] is True


def test_installed_requested_app_has_priority():
    apps = [{"name": "Pages", "path": "/Pages.app"}, {"name": "Microsoft Word", "path": "/Word.app"}]
    result = resolve_application("Word", apps)
    assert result["path"] == "/Word.app"
    assert result["fallback"] is False


def test_missing_app_and_equivalent_is_reported():
    with pytest.raises(ValueError, match="Application absente"):
        resolve_application("Word", [{"name": "Spotify", "path": "/Spotify.app"}])


def test_spoken_spaces_in_application_name():
    inventory=[{'name':'ChatGPT','path':'/Applications/ChatGPT.app'}]
    assert resolve_application('Chat GPT',inventory)['name']=='ChatGPT'


def test_store_names_are_not_confused():
    with pytest.raises(ValueError):
        resolve_application('Play Store',[{'name':'App Store','path':'/App Store.app'}])
