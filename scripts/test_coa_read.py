"""coa_read reads each lab's layout: the ids that tie a report to a lot, and the
percent results, checked against the numbers printed on real reports."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import coa_read  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "coa")


def _read(name: str) -> dict:
    with open(os.path.join(FIXTURES, name)) as f:
        return coa_read.read(f.read())


def test_smithers_two_column_terpenes_and_metrc_tag():
    r = _read("smithers_fernway.txt")
    assert r["ids"]["lab"] == "Smithers CTS"
    assert r["ids"]["metrc_tag"] == "1A4120300000285000006943"
    assert r["ids"]["lot"] == "FNY-ALPINE-T1GP-260924"
    assert r["ids"]["license"] == "OCM-PROC-24-000119"
    assert r["totals"] == {"total_thc": 90.63, "total_cbd": 0.2169, "total_cannabinoids": 94.86,
                           "total_terpenes": 2.545}
    assert r["cannabinoids"]["D9-THC"] == 90.63 and r["cannabinoids"]["THCa"] == 0.0
    # Limonene sits in the right-hand column of a two-column table.
    assert r["terpenes"]["Limonene"] == 2.311 and r["terpenes"]["Myrcene"] == 0.079
    assert abs(sum(r["terpenes"].values()) - 2.545) < 0.001


def test_kaycha_cannabinoid_grid_and_totals_row():
    r = _read("kaycha_jaunty.txt")
    assert r["ids"]["lab"] == "Kaycha Labs" and r["ids"]["lot"] == "JYVC24103B"
    assert r["cannabinoids"]["D9-THC"] == 84.423 and r["cannabinoids"]["CBG"] == 1.7562
    assert r["totals"]["total_thc"] == 84.423 and r["totals"]["total_cannabinoids"] == 88.1868
    assert r["terpenes"]["Limonene"] == 1.8 and r["terpenes"]["β-Caryophyllene"] == 1.6
    assert r["totals"]["total_terpenes"] == 6.6


def test_keystone_skips_cas_numbers():
    r = _read("keystone_revert.txt")
    assert r["ids"]["lab"] == "Keystone State Testing"
    assert r["ids"]["metrc_tag"] == "1A41203000009CE000000207"
    assert r["ids"]["source_package"] == "1A41203000009CE000000109"
    assert r["ids"]["lot"] == "CR-PP-10-ST-1"
    assert r["terpenes"]["β-Caryophyllene"] == 1.118 and r["terpenes"]["Myrcene"] == 0.0
    assert r["cannabinoids"] == {}  # a subcontracted lab's pages, not read


def test_phytofarma_average_column():
    r = _read("phytofarma_mfny.txt")
    assert r["ids"]["lab"] == "Phyto-farma" and r["ids"]["lot"] == "GZZLE3"
    assert r["ids"]["product"] == "Gazzurple Flower"
    assert r["cannabinoids"]["THCa"] == 21.74
    assert r["totals"]["total_thc"] == 19.06


def test_act_thousands_separators_and_stacked_totals():
    r = _read("act_jaunty.txt")
    assert r["ids"]["lab"] == "ACT Laboratories"
    assert r["ids"]["metrc_tag"] == "1A4120300000291000004497"
    assert r["ids"]["lot"] == "JROC-FRSA-2609" and r["ids"]["product"] == "Fruit Sangria"
    # "4,585.38" is one LOQ token, so the percent is the next one.
    assert r["cannabinoids"]["D9-THC"] == 75.607 and r["cannabinoids"]["CBG"] == 4.883
    # A note to the right of a row ("ND = Not Detected") does not hide the row.
    assert r["cannabinoids"]["THCa"] == 0.0
    assert r["totals"]["total_thc"] == 75.607 and r["totals"]["total_cannabinoids"] == 81.748
    assert r["terpenes"]["β-Caryophyllene"] == 2.556 and r["totals"]["total_terpenes"] == 7.5732


def test_an_unknown_lab_gives_ids_but_no_guessed_numbers():
    r = coa_read.read("Some Lab LLC\nMetrc Tag: 1A4120300000285000006943\nLimonene 0.1 1.5\n")
    assert r["ids"]["lab"] is None and r["ids"]["metrc_tag"] == "1A4120300000285000006943"
    assert r["terpenes"] == {} and r["cannabinoids"] == {}


def test_kaycha_newer_layout_total_is_the_percent_column():
    # "TOTAL TERPENES  11.5  0.1000  1.6200  56.7000": limit, LOQ, %, mg/unit.
    r = _read("kaycha2_electraleaf.txt")
    assert r["ids"]["lab"] == "Kaycha Labs" and r["ids"]["license"] == "OCM-PROC-24-000076"
    assert r["totals"]["total_terpenes"] == 1.62
    assert abs(sum(r["terpenes"].values()) - 1.62) < 0.001
    assert r["cannabinoids"]["THCa"] == 28.3947 and r["totals"]["total_thc"] == 26.7346


def test_cirona_reads_below_reporting_limit_as_zero():
    r = _read("cirona_cannabals.txt")
    assert r["ids"]["lab"] == "Cirona Labs" and r["ids"]["lot"] == "HE-CA-WPB-01-0924"
    # "< MRL" is one token, so CBD's percent is not shifted onto its mg column.
    assert r["cannabinoids"]["CBD"] == 0.3 and r["cannabinoids"]["THCa"] == 0.0
    assert r["totals"]["total_thc"] == 0.3 and r["totals"]["total_cannabinoids"] == 0.614
    assert r["terpenes"]["Limonene"] == 0.0
