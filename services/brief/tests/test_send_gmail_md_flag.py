# send_gmail.py --md: body-file이 Markdown으로 해석되어 HTML envelope이 메시지에 실린다
import base64
import quopri

from send_gmail import build_message_md_or_text


def test_md_flag_wraps_in_html_envelope():
    msg_dict = build_message_md_or_text(
        sender="me@a.com", to="you@b.com", subject="제목",
        body="안녕하세요.\n\n- 항목 1\n- 항목 2\n", md=True,
    )
    raw = base64.urlsafe_b64decode(msg_dict["raw"]).decode("utf-8")
    # headers and encoded body
    assert "Content-Type: text/html" in raw
    assert "<!doctype html>" in raw.lower()
    # body portion may be quoted-printable — decode to verify Korean HTML tags
    headers, _, body_encoded = raw.partition("\n\n")
    body_decoded = quopri.decodestring(body_encoded.encode("ascii")).decode("utf-8")
    assert "<li>항목 1</li>" in body_decoded


def test_md_flag_off_keeps_plain():
    msg_dict = build_message_md_or_text(
        sender=None, to="you@b.com", subject="제목",
        body="raw line\n", md=False,
    )
    raw = base64.urlsafe_b64decode(msg_dict["raw"]).decode("utf-8")
    assert "Content-Type: text/plain" in raw
    assert "raw line" in raw
