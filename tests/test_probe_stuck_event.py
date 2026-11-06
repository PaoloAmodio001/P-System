"""The probe of scripts/probe_stuck_event.py reads what it says it reads."""

from scripts.probe_stuck_event import cut_run, established_links


def test_a_probe_reads_only_the_links_it_was_asked_about(tmp_path):
    table = tmp_path / "tcp"
    table.write_text(
        "  sl  local_address rem_address   st\n"
        "   0: 0100007F:1F90 0100007F:0050 01\n"  # 8080 and 80, established
        "   1: 0100007F:1F91 0100007F:0051 0A\n"  # 8081, only listening
        "   2: 0100007F:0016 0100007F:0017 01\n"  # 22 and 23, not asked about
    )
    assert established_links({8080, 8081}, table) == {frozenset((8080, 80))}


def test_a_probe_with_no_cut_finds_nothing_stuck(tmp_path):
    class Options:
        links = 0
        wait = 30.0

    assert cut_run(tmp_path, 0, Options) == {"stuck": False}
