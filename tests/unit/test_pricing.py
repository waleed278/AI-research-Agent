from app.llm.pricing import calculate_cost_usd


def test_known_model_pricing_is_applied() -> None:
    # gpt-4o-mini: $0.15/1M input, $0.60/1M output
    cost = calculate_cost_usd("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert round(cost, 4) == round(0.15 + 0.60, 4)


def test_zero_tokens_costs_nothing() -> None:
    assert calculate_cost_usd("gpt-4o", prompt_tokens=0, completion_tokens=0) == 0.0


def test_unknown_model_falls_back_to_default_pricing_instead_of_raising() -> None:
    cost = calculate_cost_usd("some-future-model-not-in-table", prompt_tokens=1000, completion_tokens=1000)
    assert cost > 0


def test_output_tokens_cost_more_than_input_tokens_for_gpt4o() -> None:
    input_cost = calculate_cost_usd("gpt-4o", prompt_tokens=1000, completion_tokens=0)
    output_cost = calculate_cost_usd("gpt-4o", prompt_tokens=0, completion_tokens=1000)
    assert output_cost > input_cost
