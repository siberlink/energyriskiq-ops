from src.api.weekly_outlook_routes import _personalized_greeting


def test_weekly_outlook_greeting_uses_first_name():
    assert _personalized_greeting("  Ada  ") == "Hi Ada,"


def test_weekly_outlook_greeting_falls_back_without_first_name():
    assert _personalized_greeting(None) == "Hi,"
    assert _personalized_greeting("   ") == "Hi,"


def test_weekly_outlook_greeting_escapes_html():
    assert _personalized_greeting("<Ada>") == "Hi &lt;Ada&gt;,"