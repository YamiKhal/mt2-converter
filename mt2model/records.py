from dataclasses import dataclass, field


@dataclass
class Token:
    kind: str
    text: str = ""

    def render(self) -> str:
        if self.kind == "string":
            escaped = self.text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

            return f'"{escaped}"'
        if self.kind == "semicolon":
            return ";"
        if self.kind == "equals":
            return "="

        return self.text


@dataclass
class Record:
    label: str | None = None
    tokens: list[Token] = field(default_factory=list)
    children: list["Record"] = field(default_factory=list)
    had_block: bool = False
    in_block: bool = False
    line_open: bool = True

    def values(self) -> list[Token]:
        return [t for t in self.tokens if t.kind != "semicolon"]

    def texts(self) -> list[str]:
        return [t.text for t in self.values() if t.kind not in ("equals",)]

    def floats(self) -> list[float]:
        return [float(t) for t in self.texts()]

    def vector(self) -> tuple[float, float, float]:
        values = self.floats()

        return (values[0], values[1], values[2])

    def first(self) -> str | None:
        texts = self.texts()

        return texts[0] if texts else None

    def child(self, label: str) -> "Record | None":
        return next((c for c in self.children if c.label == label), None)

    def children_named(self, label: str) -> list["Record"]:
        return [c for c in self.children if c.label == label]

    def prop(self, label: str) -> str | None:
        found = self.child(label)

        return found.first() if found else None

    def set_prop(self, label: str, *values, quoted: bool = True):
        tokens = [_value_token(v, quoted) for v in values] + [Token("semicolon")]
        found = self.child(label)
        if found:
            found.tokens = tokens
        else:
            self.children.append(Record(label, tokens))


_OPEN = object()
_CLOSE = object()
_NEWLINE = object()


def _value_token(value, quoted: bool) -> Token:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Token("number", _number(value))
    if quoted:
        return Token("string", str(value))

    return Token("label", str(value))


def _number(value) -> str:
    if isinstance(value, int):
        return str(value)

    return f"{value:.6f}"


def _is_ws(c: str) -> bool:
    return c in " \t,"


def _is_alpha(c: str) -> bool:
    return c.isascii() and (c.isalpha() or c == "_")


def _is_numeric(c: str) -> bool:
    return c in ".-+" or (c.isascii() and c.isdigit())


def _float_prefix(s: str) -> int | None:
    i = 0
    if i < len(s) and s[i] in "+-":
        i += 1
    start = i
    while i < len(s) and s[i].isdigit():
        i += 1
    digits = i - start
    if i < len(s) and s[i] == ".":
        i += 1
        frac = i
        while i < len(s) and s[i].isdigit():
            i += 1
        digits += i - frac
    if digits == 0:
        return None
    if i < len(s) and s[i] in "eE":
        j = i + 1
        if j < len(s) and s[j] in "+-":
            j += 1
        exp = j
        while j < len(s) and s[j].isdigit():
            j += 1
        if j > exp:
            i = j

    return i


def _int_prefix(s: str) -> int | None:
    i = 0
    if i < len(s) and s[i] in "+-":
        i += 1
    start = i
    while i < len(s) and s[i].isdigit():
        i += 1

    return i if i > start else None


def _extract(s: str):
    i = 0
    while i < len(s) and _is_ws(s[i]):
        i += 1
    s = s[i:]
    if not s:
        return None, ""
    c = s[0]
    if c == '"':
        out, i, escaped = [], 1, False
        while i < len(s) and s[i] != "\0":
            ch = s[i]
            if escaped:
                out.append("\n" if ch == "n" else ch)
                escaped = False
            elif ch == '"':
                break
            elif ch == "\\":
                escaped = True
            else:
                out.append(ch)
            i += 1

        return Token("string", "".join(out)), s[i + 1 :]
    if c == "{":
        return _OPEN, s[1:]
    if c == "}":
        return _CLOSE, s[1:]
    if c == ";":
        return Token("semicolon"), s[1:]
    if _is_alpha(c):
        i = 0
        while i < len(s) and (_is_alpha(s[i]) or _is_numeric(s[i])):
            i += 1

        return Token("label", s[:i]), s[i:]
    if _is_numeric(c):
        run = 0
        while run < len(s) and _is_numeric(s[run]):
            run += 1
        n = _float_prefix(s) if "." in s[:run] else None
        if n is None:
            n = _int_prefix(s)
        if n is not None:
            return Token("number", s[:n]), s[n:]
    if c == "#":
        return None, ""
    if c == "=":
        return Token("equals"), s[1:]
    i = 0
    while i < len(s) and not _is_ws(s[i]):
        i += 1

    return Token("bare", s[:i]), s[i:]


def _append(record: Record, token) -> bool:
    if not record.in_block:
        if isinstance(token, Token) and token.kind == "label" and not record.tokens and record.label is None:
            record.label = token.text
        elif token is _OPEN:
            record.in_block = True
            record.had_block = True
        elif token is _CLOSE:
            return False
        elif token is _NEWLINE:
            if record.label is not None or record.tokens:
                if record.line_open:
                    record.line_open = False

                    return True

                return False
        elif record.line_open:
            record.tokens.append(token)
        else:
            return False

        return True
    if token is _CLOSE:
        taken = _append(record.children[-1], _CLOSE) if record.children else False
        if not taken:
            record.in_block = False
            record.line_open = False
    elif token is _NEWLINE:
        if record.children:
            _append(record.children[-1], _NEWLINE)
    else:
        taken = _append(record.children[-1], token) if record.children else False
        if not taken:
            child = Record()
            _append(child, token)
            record.children.append(child)

    return True


def _parse_line(record: Record, line: str) -> bool:
    valid = False
    while line:
        token, line = _extract(line)
        if token is not None:
            valid = True
            _append(record, token)
    _append(record, _NEWLINE)

    return valid


def _split_lines(text: str) -> list[str]:
    lines, current, pending = [], [], False
    for c in text:
        pending = True
        if c in "\n\0":
            lines.append("".join(current))
            current = []
            pending = False
        elif c != "\r":
            current.append(c)
    if pending:
        lines.append("".join(current))

    return lines


def _starts_with_open(line: str) -> bool:
    return _extract(line)[0] is _OPEN


def _finish(record: Record):
    for child in record.children:
        _finish(child)
    record.in_block = False
    record.line_open = False


def parse(data: bytes | str) -> list[Record]:
    text = data if isinstance(data, str) else _decode(data)
    lines = _split_lines(text)
    records, i = [], 0
    while True:
        record = Record()
        valid = done = False
        have_line = True
        while have_line and (not valid or not done):
            done = True
            if i < len(lines):
                line = lines[i]
                i += 1
                if i < len(lines) and _starts_with_open(lines[i]):
                    line += lines[i]
                    i += 1
                valid = _parse_line(record, line)
                if record.in_block:
                    done = False
            else:
                have_line = False
                if record.in_block:
                    raise ValueError(f"end of file inside an unclosed block (record {record.label!r})")
        if not valid:
            break
        _finish(record)
        records.append(record)

    return records


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _write(record: Record, out: list[str], depth: int):
    tabs = "\t" * depth
    line = tabs
    first = True
    if record.label is not None:
        line += record.label
        first = False
    for token in record.tokens:
        if not first and token.kind != "semicolon":
            line += " "
        line += token.render()
        first = False
    out.append(line + "\n")
    if record.children or record.had_block:
        out.append(tabs + "{\n")
        for child in record.children:
            _write(child, out, depth + 1)
        out.append(tabs + "}\n")


def render(records: list[Record]) -> str:
    out: list[str] = []
    for record in records:
        _write(record, out, 0)

    return "".join(out)


def block(label: str, *children: Record) -> Record:
    return Record(label, children=list(children), had_block=True, line_open=False)


def leaf(label: str, *values, quoted: bool = True, semicolon: bool = True) -> Record:
    tokens = [_value_token(v, quoted) for v in values]
    if semicolon:
        tokens.append(Token("semicolon"))

    return Record(label, tokens, line_open=False)


def vector_line(values, semicolon: bool = True) -> Record:
    tokens = [Token("number", _number(float(v))) for v in values]
    if semicolon:
        tokens.append(Token("semicolon"))

    return Record(None, tokens, line_open=False)
