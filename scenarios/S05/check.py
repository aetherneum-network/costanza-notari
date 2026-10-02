"""S05 - Lawyer writes via PEC gateway on behalf of a creditor (Officine Lagorai S.r.l.).
Pass: author, transmitter and party distinct; 100 % correct attribution despite misleading file names (L5)."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from scenarios._common import ensure_corpus, load, main, report, run_pipeline, workdir  # noqa: E402
from pipeline import s6_consolidate  # noqa: E402
from pipeline.entities import Debtor  # noqa: E402


def check():
    ensure_corpus()
    w = workdir("S05")
    code, _ = run_pipeline(HERE / "input" / "corpus", w, config=HERE / "input" / "config.json",
                           as_of="2026-10-21T09:40:00+02:00")
    exp = load(HERE / "expected" / "expected.json")
    recs = {r["envelope"]: r for r in load(w / "work" / "state" / "06_consolidation.json")["records"]}
    fields = ("sender_class", "transmitter_entity", "author_entity", "party_entity", "counterparty_channel")
    wrong = [(env, f, recs[env][f], v) for env, e in exp["envelopes"].items() for f, v in e.items() if recs[env][f] != v]
    e1 = recs["envelopes/2026-10/PEC_S05_E1.eml"]
    distinct = len({e1["transmitter_entity"], e1["author_entity"], e1["party_entity"]}) == 3
    debtor = Debtor(load(HERE / "input" / "config.json")["debtor"])
    no_debtor = not any(debtor.is_debtor_name(r[f]) for r in recs.values() for f in fields[1:4]) and \
        not any(debtor.is_debtor_address(r["counterparty_channel"]) for r in recs.values())
    auth = {p.name: s6_consolidate.resolve_author(load(p)) for p in sorted((HERE / "input" / "handoff_files").glob("*.json"))}
    auth_ok = sum(auth[k] == v for k, v in exp["authorship"].items())
    ok = code == 0 and not wrong and distinct and no_debtor and auth_ok == len(exp["authorship"])
    return report("S05", ok, f"E1 transmitter={e1['transmitter_entity']} | author={e1['author_entity']} | "
                  f"party={e1['party_entity']} (distinct: {distinct}); channel {e1['counterparty_channel']}; "
                  f"debtor never attributed: {no_debtor}; file-name vs fields attribution {auth_ok}/{len(exp['authorship'])}; "
                  f"field mismatches {len(wrong)}", {"wrong": wrong, "authorship": auth})


if __name__ == "__main__":
    main(check)
