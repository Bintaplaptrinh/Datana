from app.providers.tiktok import clean_comment_text


def test_clean_comment_matches_comment_workflow() -> None:
    assert clean_comment_text("@author Great pipeline [sticker]") == "Great pipeline"
    assert clean_comment_text("@author [sticker]") is None
