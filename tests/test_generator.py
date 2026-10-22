from idemtest.generator import parse_scenarios


def test_parse_drops_invalid_and_strips_fences():
    text = '```json\n{"scenarios":[{"name":"ok","steps":[{"method":"GET","path":"/payments/x"}]},{"name":"bad","steps":[]}]}\n```'
    good, dropped = parse_scenarios(text)
    assert len(good) == 1 and dropped == 1
