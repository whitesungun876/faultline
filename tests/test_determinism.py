from faultline.bundle import score_bundle


CASE_DIR = "generated_cases/day1_45"


def test_reset_corpus_determinism():
    """With a reset corpus, scores and signatures are bit-for-bit deterministic."""
    r1 = score_bundle(CASE_DIR, corpus={})
    r2 = score_bundle(CASE_DIR, corpus={})

    assert [x["score"] for x in r1] == [x["score"] for x in r2]
    assert [x.get("signature") for x in r1] == [x.get("signature") for x in r2]
    assert [x.get("fine_signature") for x in r1] == [x.get("fine_signature") for x in r2]


def test_persisted_corpus_decays():
    """With a persisted corpus, a second pass over the same VALID cluster decays."""
    corpus = {}
    r1 = score_bundle(CASE_DIR, corpus)
    r2 = score_bundle(CASE_DIR, corpus)

    for first, second in zip(r1, r2):
        if first["gate"] == "VALID":
            assert second["score"] < first["score"]
            assert second["signature"] == first["signature"]
