from app.agent.state import EvidenceStore


def test_evidence_store_assigns_sequential_ids_and_dedupes_by_url() -> None:
    store = EvidenceStore()
    a = store.add("https://a.com", "A", "snippet a")
    b = store.add("https://b.com", "B", "snippet b")
    a_again = store.add("https://a.com", "A dup title", "different snippet")

    assert a.id == 1
    assert b.id == 2
    assert a_again.id == 1  # same URL returns the original item, not a new id
    assert len(store.items) == 2


def test_evidence_store_enforces_max_items_budget() -> None:
    store = EvidenceStore(max_items=2)
    store.add("https://a.com", "A", "s")
    store.add("https://b.com", "B", "s")
    overflow = store.add("https://c.com", "C", "s")

    assert overflow.id == -1
    assert len(store.items) == 2
    assert "https://c.com" not in [i.url for i in store.items]


def test_prompt_block_lists_items_in_id_order() -> None:
    store = EvidenceStore()
    store.add("https://b.com", "B", "snippet b")
    store.add("https://a.com", "A", "snippet a")
    block = store.as_prompt_block()

    assert block.index("[1]") < block.index("[2]")
