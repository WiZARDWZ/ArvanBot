from arvan_orchestrator.security.redaction import REDACTION_PLACEHOLDER, redact_secrets, redact_text


def test_authorization_header_redaction_removes_header_value() -> None:
    raw = "GET / HTTP/1.1\nAuthorization: apikey real-machine-user-key\nAccept: application/json"

    redacted = redact_text(raw)

    assert "real-machine-user-key" not in redacted
    assert f"Authorization: {REDACTION_PLACEHOLDER}" in redacted
    assert "Accept: application/json" in redacted


def test_secret_redaction_removes_common_secret_keys_recursively() -> None:
    payload = {
        "token": "real-token",
        "nested": {
            "db_password": "real-password",
            "private_key": "-----BEGIN PRIVATE KEY-----real-key",
            "safe": "kept",
        },
        "items": [{"client_secret": "real-secret"}, {"credential_id": "real-credential"}],
    }

    redacted = redact_secrets(payload)

    assert redacted["token"] == REDACTION_PLACEHOLDER
    assert redacted["nested"]["db_password"] == REDACTION_PLACEHOLDER
    assert redacted["nested"]["private_key"] == REDACTION_PLACEHOLDER
    assert redacted["nested"]["safe"] == "kept"
    assert redacted["items"][0]["client_secret"] == REDACTION_PLACEHOLDER
    assert redacted["items"][1]["credential_id"] == REDACTION_PLACEHOLDER


def test_arvan_machine_user_key_redaction_removes_apikey_values() -> None:
    redacted = redact_text("provider key is apikey live-machine-user-key")

    assert "live-machine-user-key" not in redacted
    assert f"apikey {REDACTION_PLACEHOLDER}" in redacted
