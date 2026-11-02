from app.core.splits import candidate_patterns, choose_preferred, parse_pattern_list, partitions


def test_parse_patterns():
    assert parse_pattern_list("3+3+3; 2+2+2+3") == [(3, 3, 3), (3, 2, 2, 2)]
    assert parse_pattern_list("") == []


def test_partitions_respect_bounds():
    pats = partitions(9, 2, 3, 99)
    assert (3, 3, 3) in pats and (3, 2, 2, 2) in pats
    assert all(2 <= x <= 3 for p in pats for x in p)


def test_allowed_and_forbidden():
    assert candidate_patterns(7, 1, 4, "3+2+2; 4+3; 2+2+2+1") == [(3, 2, 2), (4, 3), (2, 2, 2, 1)]
    assert candidate_patterns(7, 1, 4, "3+2+2; 4+3", forbidden_text="4+3") == [(3, 2, 2)]
    assert all(len(p) <= 2 for p in candidate_patterns(7, 1, 4, max_parts=2))


def test_preferred():
    pats = candidate_patterns(9, 1, 3)
    assert choose_preferred(9, pats, "", 1, 3) == (3, 3, 3)
    assert choose_preferred(9, pats, "3+2+2+2", 1, 3) == (3, 2, 2, 2)
