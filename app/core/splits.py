import math

Pattern = tuple[int, ...]


def parse_pattern(text: str) -> Pattern:
    text = text.strip()
    if not text:
        raise ValueError("boş bölünme")
    parts = [p.strip() for p in text.replace("x", "+").split("+")]
    values = []
    for p in parts:
        if not p.isdigit() or int(p) <= 0:
            raise ValueError(f"hatalı bölünme: {text}")
        values.append(int(p))
    return tuple(sorted(values, reverse=True))


def parse_pattern_list(text: str | None) -> list[Pattern]:
    if not text or not str(text).strip():
        return []
    result = []
    for chunk in str(text).replace("\n", ";").replace(",", ";").split(";"):
        if chunk.strip():
            pat = parse_pattern(chunk)
            if pat not in result:
                result.append(pat)
    return result


def format_pattern(pattern: Pattern) -> str:
    return "+".join(str(p) for p in pattern) if pattern else "-"


def partitions(total: int, min_part: int, max_part: int, max_parts: int) -> list[Pattern]:
    result: list[Pattern] = []

    def rec(remaining: int, largest: int, acc: list[int]):
        if remaining == 0:
            result.append(tuple(acc))
            return
        if len(acc) >= max_parts:
            return
        for part in range(min(largest, remaining), min_part - 1, -1):
            rest = remaining - part
            if rest != 0 and rest < min_part:
                continue
            acc.append(part)
            rec(rest, part, acc)
            acc.pop()

    if total > 0 and max_part >= min_part >= 1:
        rec(total, max_part, [])
    return result


def balanced_pattern(total: int, min_part: int, max_part: int) -> Pattern | None:
    if total <= 0:
        return ()
    k = math.ceil(total / max_part)
    base, rem = divmod(total, k)
    if base < min_part:
        return None
    return tuple([base + 1] * rem + [base] * (k - rem))


def candidate_patterns(hours: int, min_block: int, max_block: int, allowed_text: str = "",
                       forbidden_text: str = "", max_parts: int = 99) -> list[Pattern]:
    if hours <= 0:
        return [()]
    max_block = max(1, min(max_block, hours))
    min_block = max(1, min(min_block, max_block))
    forbidden = set(parse_pattern_list(forbidden_text))
    allowed = [p for p in parse_pattern_list(allowed_text) if sum(p) == hours and len(p) <= max_parts]
    if allowed:
        candidates = allowed
    else:
        candidates = partitions(hours, min_block, max_block, max_parts)
    return [p for p in candidates if p not in forbidden]


def choose_preferred(hours: int, candidates: list[Pattern], preferred_text: str, min_block: int,
                     max_block: int) -> Pattern | None:
    if not candidates:
        return None
    for pat in parse_pattern_list(preferred_text):
        if sum(pat) == hours and pat in candidates:
            return pat
    bal = balanced_pattern(hours, max(1, min_block), max(1, min(max_block, hours)))
    if bal in candidates:
        return bal
    return min(candidates, key=lambda p: (len(p), max(p) - min(p)))
