import re


def format_ai_response(text: str) -> str:
    result = ""
    last_end = 0

    for m in re.finditer(r"```(\w*)\n(.*?)```", text, re.DOTALL):
        result += _inline_to_html(text[last_end : m.start()])
        lang = _escape(m.group(1))
        code = _escape(m.group(2))
        if lang:
            result += f'<pre><code class="language-{lang}">{code}</code></pre>'
        else:
            result += f"<pre>{code}</pre>"
        last_end = m.end()

    result += _inline_to_html(text[last_end:])
    return result


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _repl(tag: str):
    def wrap(m):
        return f"<{tag}>{_inline_to_html(m.group(1))}</{tag}>"
    return wrap


_patterns = [
    (r"`([^`]+)`", lambda m: f"<code>{_escape(m.group(1))}</code>"),
    (r"\|\|(.+?)\|\|", _repl("tg-spoiler")),
    (r"~~(.+?)~~", _repl("s")),
    (r"\*\*(.+?)\*\*", _repl("b")),
    (r"__(.+?)__", _repl("b")),
    (r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", _repl("i")),
    (r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", _repl("i")),
    (r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{_escape(m.group(2))}">{_inline_to_html(m.group(1))}</a>'),
]


def _inline_to_html(text: str) -> str:
    if not text:
        return ""

    result = ""
    i = 0
    while i < len(text):
        if text[i] == "#" and (i == 0 or text[i - 1] == "\n"):
            m = re.match(r"^#{1,6}\s+(.*)", text[i:])
            if m:
                result += f"<b>{_inline_to_html(m.group(1))}</b>"
                i += m.end()
                continue

        if text[i] == ">" and (i == 0 or text[i - 1] == "\n"):
            line_end = text.find("\n", i)
            if line_end == -1:
                line_end = len(text)
            result += f"<blockquote>{_inline_to_html(text[i + 1 : line_end].lstrip())}</blockquote>"
            i = line_end
            continue

        matched = False
        for pattern, repl in _patterns:
            m = re.match(pattern, text[i:])
            if m:
                result += repl(m)
                i += m.end()
                matched = True
                break

        if not matched:
            result += _escape(text[i])
            i += 1

    return result
