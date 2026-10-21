import pytest
from app.telegram_client.parser import (
    normalize_channel_input,
    is_ad_message,
    build_post_url,
    extract_media_type,
    extract_reactions_count,
)
from app.core.security import sanitize_excel_cell


def test_normalize_channel_input():
    # Public channel URLs
    assert normalize_channel_input("https://t.me/mychannel") == "mychannel"
    assert normalize_channel_input("https://t.me/mychannel/") == "mychannel"
    assert normalize_channel_input("https://t.me/s/mychannel") == "mychannel"
    assert normalize_channel_input("https://t.me/s/mychannel/") == "mychannel"
    assert normalize_channel_input("https://t.me/mychannel?start=123") == "mychannel"
    assert normalize_channel_input("http://telegram.me/mychannel") == "mychannel"
    
    # Username with @
    assert normalize_channel_input("@mychannel") == "mychannel"
    assert normalize_channel_input("mychannel") == "mychannel"

    # Private join links
    assert normalize_channel_input("https://t.me/+AbCdEf123") == "+AbCdEf123"
    assert normalize_channel_input("https://t.me/joinchat/AbCdEf123") == "+AbCdEf123"


def test_is_ad_message_direct_keyword():
    text = "IMKON savdo markazida katta aksiya! Murojaat uchun: @imkonhelpbot"
    assert is_ad_message(text, keywords=["@imkonhelpbot"]) is True


def test_is_ad_message_case_insensitivity():
    # Capitalized / uppercase variations
    assert is_ad_message("Batafsil: @ImkonHelpBot", keywords=["@imkonhelpbot"]) is True
    assert is_ad_message("Batafsil: @IMKONHELPBOT", keywords=["@imkonhelpbot"]) is True
    assert is_ad_message("Savollar bo'yicha: t.me/imkonhelpbot", keywords=["@imkonhelpbot"]) is True
    assert is_ad_message("Oddiy post hech qanday reklamasiz", keywords=["@imkonhelpbot"]) is False


def test_is_ad_message_in_media_caption():
    caption = "Yangi muzlatgichlar keldi! Narxlar arzon. Bog'lanish: @imkonhelpbot"
    assert is_ad_message(caption) is True


def test_is_ad_message_via_entities():
    # Text with clickable link entity
    text = "Aksiyamiz haqida ma'lumot olish uchun bu yerni bosing"
    
    class DummyEntity:
        def __init__(self, url):
            self.url = url

    entities = [DummyEntity("https://t.me/imkonhelpbot")]
    assert is_ad_message(text, entities=entities, keywords=["@imkonhelpbot"]) is True

    # Entity without target url
    entities_none = [DummyEntity("https://google.com")]
    assert is_ad_message(text, entities=entities_none, keywords=["@imkonhelpbot"]) is False


def test_build_post_url():
    # Public channel
    assert build_post_url(123456, "mychannel", 100) == "https://t.me/mychannel/100"
    assert build_post_url(123456, "@mychannel", 100) == "https://t.me/mychannel/100"

    # Private channel
    assert build_post_url(-1001987654321, None, 55) == "https://t.me/c/1987654321/55"


def test_sanitize_excel_cell_prevents_injection():
    # Excel formula injection attacks: =, +, -, @, \t, %
    assert sanitize_excel_cell("=1+1") == "'=1+1"
    assert sanitize_excel_cell("+SUM(A1:A10)") == "'+SUM(A1:A10)"
    assert sanitize_excel_cell("-1234") == "'-1234"
    assert sanitize_excel_cell("@imkonhelpbot") == "'@imkonhelpbot"
    assert sanitize_excel_cell("Oddiy matn") == "Oddiy matn"
    assert sanitize_excel_cell(12345) == 12345
