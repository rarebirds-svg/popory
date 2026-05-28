# Markdown(GFM) → 메일 클라이언트가 안전히 렌더하는 self-contained HTML envelope
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

_ENVELOPE_HEAD = """<!doctype html><html lang="ko"><meta charset="utf-8">
<style>
  body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;
       max-width:680px;margin:24px auto;padding:0 16px;color:#111;
       line-height:1.65;font-size:15px;}
  h2,h3{margin-top:1.5em;}
  pre{background:#f6f8fa;padding:12px;border-radius:6px;overflow:auto;}
  blockquote{border-left:4px solid #d0d7de;color:#444;padding-left:12px;margin:0;}
  table{border-collapse:collapse;}
  th,td{border:1px solid #d0d7de;padding:6px 10px;}
  a{color:#0a66c2;}
</style>
<body>
"""
_ENVELOPE_FOOT = "</body></html>"


def _make_md() -> MarkdownIt:
    md = MarkdownIt("gfm-like", {"linkify": False, "html": False, "typographer": False})
    md.enable("table")
    md.enable("strikethrough")
    md.use(tasklists_plugin)
    return md


def markdown_to_email_html(src: str) -> str:
    """Markdown 본문을 메일 발송용 self-contained HTML로 변환."""
    body = _make_md().render(src)
    return _ENVELOPE_HEAD + body + _ENVELOPE_FOOT
