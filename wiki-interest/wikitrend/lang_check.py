"""Cheap check of Ukrainian text for Russianisms, calques and stray English words.

Used by `report` (warnings go back to the agent, which rewrites and reruns) and by
the evals. It is a list of known traps, not a grammar checker: an empty result
means "none of the usual mistakes", not "perfect Ukrainian".
"""
from __future__ import annotations

import re

CYR = re.compile(r"[а-яіїєґА-ЯІЇЄҐʼ']")
LAT_WORD = re.compile(r"(?<![\w/.\-])[A-Za-z][A-Za-z\-]{2,}(?![\w/\-])")

# (regex, what to write instead). Case-insensitive, whole words.
BANNED = [
    (r"[ыэъё]", "російські літери (ы, э, ъ, ё)"),
    (r"\b(что|это|также|сейчас|если|только|между|всего|более|однако|потому что)\b",
     "російське слово"),
    (r"(?<![\w-])и(?![\w-])", "«і», «й» або «та» замість російського «и»"),
    (r"\bроку на року\b|\bрік на рік\b", "«рік до року»"),
    (r"\bзнаходит[ьс]ся\b|\bзнаходяться\b|\bзнаходил[аио]?с[ья]\b",
     "«перебуває», «є» або «у межах»"),
    (r"\bвидання\b|\bвиданн[іяю]\w*", "«мовний розділ» (якщо йдеться про Вікіпедію)"),
    (r"\bвпевненіст\w*", "«довіра до висновку» (як у звіті)"),
    (r"\bпо (мов|тем|місяц|країн|розділ)\w*", "«за мовами», «за темами», «щодо …»"),
    (r"\d+,\d+ рази\b", "«у N,N раза» (з дробовими числами)"),
    (r"\bна протязі\b", "«протягом»"),
    (r"\bсклада(є|ють|ло|в|ла)(?=\s+[−\-+~≈]?\s?\d)", "«становить» (про числа)"),
    (r"\bявля(є|ю)ться\b", "«є»"),
    (r"\bслідуюч\w+", "«наступний»"),
    (r"\bспівпада\w*", "«збігається»"),
    (r"\bв якості\b", "«як»"),
    (r"\bна даний момент\b", "«наразі», «зараз»"),
    (r"\bу відповідності\b|\bв відповідності\b", "«відповідно до»"),
    (r"\bдякуючи\b", "«завдяки»"),
    (r"\bсезонн\w+ модел\w*", "«сезонність»"),
    (r"\bзнахідк\w*", "«висновки», «результати»"),
    (r"\bв районі \d", "«близько»"),
    (r"\bспівставл\w*", "«зіставлення», «порівняння»"),
    (r"\bприйма\w* участь\b", "«брати участь»"),
    (r"\b(той|та|те|ті|тих|тим|тими|того|тому|тієї|тій|ту|так\w*) же\b", "«той самий», «з тих самих причин», «такий самий»"),
    (r"\bпереглядач\w*", "«перегляди» (статей)"),
    (r"\bвідносно до\b", "«порівняно з», «відносно»"),
    (r"\bWikipedia\b", "«Вікіпедія» у тексті (Wikipedia лише в назвах)"),
    (r"\b\w+[аяую]юч(ий|а|е|і|их|ого|ій|ому|им|ими)\b",
     "дієприкметник на -ючий: «що зростає», «спадний», «наявний» (не «зростаючий», "
     "«спадаючий», «існуючий»)"),
    (r"\b(вижу|растущ\w*|растуч\w*|нужн\w*|сейчас|пока что|кажд\w*)\b",
     "російське слово"),
    (r"\bобумовлен\w*", "«зумовлений»"),
    (r"\b(раст[уеё]\w*|провер\w*|спрос\w*|отслід\w*|отслеж\w*)", "російське слово (зрост-, перевір-, відстеж-)"),
    (r"\b\w+мовній розділі\b", "«у польськомовному розділі» (розділ — чоловічий рід)"),
]
BANNED_RE = [(re.compile(p, re.IGNORECASE), fix) for p, fix in BANNED]

# Latin words that are fine inside a Ukrainian sentence.
ALLOWED_LATIN = {
    "wikimedia", "wikidata", "pdf", "api", "json", "png", "csv", "url", "ci",
    "google", "trends", "yoy", "mk_p", "per_million", "all", "topics",
}


NUM_VIEWS = re.compile(r"(?<![\d,.])(\d{1,3}(?:[  ]\d{3})*|\d+)\s+переглядів\b")


def _needs_other_form(number: str) -> bool:
    """True if a whole number must not be followed by «переглядів» (genitive plural)."""
    n = int(re.sub(r"\D", "", number))
    return n % 10 in (1, 2, 3, 4) and n % 100 not in (11, 12, 13, 14)


def is_ukrainian(text: str) -> bool:
    cyr = len(CYR.findall(text))
    return cyr > 20 and cyr > len(re.findall(r"[A-Za-z]", text))


def _prose(text: str) -> str:
    """Drop code, paths, URLs and quoted titles — keep the sentences."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"https?://\S+|(?<![\w/])[.~]?/[\w./\-]+|[\w\-]+\.(png|pdf|json|py|md)\b",
                  " ", text)  # URLs and file paths
    text = re.sub(r"«[^»]*»|\"[^\"]*\"", " ", text)   # quoted titles/terms
    return text


def check_uk(text: str, allow: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """Return human-readable warnings; [] if the text is not Ukrainian or looks clean.

    `allow`: extra words that may appear in Latin script (article titles, topic names).
    """
    if not is_ukrainian(text):
        return []
    prose = _prose(text)
    out = []
    for rx, fix in BANNED_RE:
        found = sorted({m.group(0).strip() for m in rx.finditer(prose)})
        if found:
            out.append(f"{', '.join(found)} → {fix}")
    bad_num = sorted({m.group(0) for m in NUM_VIEWS.finditer(prose)
                      if _needs_other_form(m.group(1))})
    if bad_num:
        out.append(f"{', '.join(bad_num)} → узгодження: «1 перегляд», «2–4 перегляди», "
                   f"«5 переглядів», «131 перегляд», «953 перегляди» (або «переглядів за "
                   f"день: 953»)")
    ok = {w.lower() for w in ALLOWED_LATIN} | {w.lower() for w in allow}
    latin = []
    for line in prose.splitlines():
        if not CYR.search(line):
            continue
        for w in LAT_WORD.findall(line):
            if w.lower() not in ok and not re.fullmatch(r"[A-Z]{2,}|Q\d+", w):
                latin.append(w)
    latin = [w for w in latin if w.lower() != "wikipedia"]  # reported above
    if latin:
        out.append(f"{', '.join(dict.fromkeys(latin))} → англійські слова посеред "
                   f"українського речення: перекладіть або візьміть у лапки назву статті")
    return out


def allowed_words(*texts: str) -> set[str]:
    """Latin words from tool output (article titles, ids) that the answer may repeat."""
    return {w.lower() for t in texts for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", t)}
