from . import records


def strings_path(mod_id: str, language: str = "english") -> str:
    return f"i18n/{language}/{mod_id}_models.vrt"


def set_strings(existing: str, values: dict[str, str]) -> str:
    parsed = records.parse(existing) if existing else []
    for key, text in values.items():
        line = records.leaf(key, text, semicolon=False)
        index = next((i for i, r in enumerate(parsed) if r.label == key), None)
        if index is None:
            parsed.append(line)
        else:
            parsed[index] = line

    return records.render(parsed)
