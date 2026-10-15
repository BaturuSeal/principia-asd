import csv
import hashlib
import io
import json
import zipfile
from copy import deepcopy

import numpy as np
import pytest

from principia_asd.catalog import ppg
from principia_asd.catalog.native import reconstruct
from principia_asd.io import file_sha


def waveform(sid="112001", flat=False, red_first=True):
    t = np.arange(300) / 30
    red = np.round(1000 * np.sin(2 * np.pi * 1.5 * t)).astype("<i2")
    if flat:
        header = f"{sid}_PPG 300 30 1\n" + "\n".join(
            f"{sid}_PPG.dat 16 1({-int(v)})/a.u. 0 0 0 0 0" for v in red
        )
        payload = np.zeros(300, dtype="<i2").tobytes()
    else:
        names = ["PPG_R", "PPG_G", "PPG_B"] if red_first else ["PPG_G", "PPG_B", "PPG_R"]
        header = f"{sid}_PPG 3 30 300\n" + "\n".join(
            f"{sid}_PPG.dat 16 1(0)/a.u. 0 0 0 0 0 {name}" for name in names
        )
        payload = np.array(
            [red if n == "PPG_R" else red[::-1] // 2 for n in names], dtype="<i2"
        ).T.tobytes()
    return header.encode(), payload, red.astype(float)


def csv_bytes(rows):
    f = io.StringIO()
    writer = csv.writer(f)
    writer.writerows(rows)
    return ("\ufeff" + f.getvalue()).encode()


def entries():
    meta, ann = [ppg.META_HEADER], [["ID", "Quality", "HR"]]
    result, records = {}, []
    for sid, flat in [("100001", True), ("100002", True), ("112001", False)]:
        head, data, _ = waveform(sid, flat)
        stem = sid + "/" + sid + "_PPG"
        result[stem + ".hea"], result[stem + ".dat"] = head, data
        records.append(stem)
        ann.append([sid, "0", "90"])
        meta.append([sid, "F", "40", "", "", "1", "2;3", "", "", ""])
    # Unread ECG file deliberately has invalid content; it must not be decoded.
    result["100001/100001_ECG.hea"] = b"Not a decodable ECG header"
    result["100001/100001_ECG.dat"] = b"Untrusted unneeded response waveform"
    records.append("100001/100001_ECG")
    result["RECORDS.txt"] = "\n".join(records).encode()
    result["quality-hr-ann.csv"] = csv_bytes(ann)
    result["subject-info.csv"] = csv_bytes(meta)
    return result


def save(tmp_path, original):
    d = deepcopy(original)
    d["SHA256SUMS.txt"] = "\n".join(
        hashlib.sha256(b).hexdigest() + " " + n for n, b in d.items()
    ).encode()
    path = tmp_path / "signals.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in d.items():
            z.writestr(ppg.PREFIX + n, b)
    return path


@pytest.mark.parametrize("flat,red_first", [(True, True), (False, True), (False, False)])
def test_native_layout_gain_units_and_channel_identity(flat, red_first):
    header, data, expected = waveform(flat=flat, red_first=red_first)
    signal, info = ppg.decode_ppg(header, data, "112001")
    assert np.array_equal(signal, expected)
    assert info["interpreted_samples"] == 300 and info["sample_rate_hz"] == 30
    assert info["header_frames"] == (1 if flat else 300)
    features = ppg.signal_features(signal)
    assert abs(features["fft_bpm"] - 90) < 0.5
    assert features["acf_bpm"] == 90 and features["spectral_quality"] > 0.8


def test_channel_and_segment_locality():
    h, d, _ = waveform()
    signal, _ = ppg.decode_ppg(h, d, "112001")
    other = np.frombuffer(d, dtype="<i2").copy().reshape(300, 3)
    other[:, 1:] = 123
    changed, _ = ppg.decode_ppg(h, other.tobytes(), "112001")
    assert ppg.signal_features(signal) == ppg.signal_features(changed)
    shifted = ppg.signal_features(2 * signal + 10 + np.arange(300) * 0.2)
    assert all(
        np.isclose(v, shifted[k], atol=1e-10) for k, v in ppg.signal_features(signal).items()
    )


@pytest.mark.parametrize(
    "fault", ["gain", "unit", "rate", "format", "file", "shape", "colour", "sentinel", "nonfinite"]
)
def test_reject_invalid_native_signal(fault):
    h, d, _ = waveform()
    if fault == "gain":
        h = h.replace(b"1(0)/", b"0(0)/")
    elif fault == "unit":
        h = h.replace(b"/a.u.", b"/mV")
    elif fault == "rate":
        h = h.replace(b"3 30 300", b"3 60 300")
    elif fault == "format":
        h = h.replace(b" 16 ", b" 212 ")
    elif fault == "file":
        h = h.replace(b"112001_PPG.dat", b"../secret.dat")
    elif fault == "shape":
        d = d[:-2]
    elif fault == "colour":
        h = h.replace(b"PPG_R", b"PPG_B")
    elif fault == "nonfinite":
        h = h.replace(b"1(0)/", b"nan(0)/")
    else:
        a = np.frombuffer(d, dtype="<i2").copy()
        a[0] = -32768
        d = a.tobytes()
    with pytest.raises(ValueError):
        ppg.decode_ppg(h, d, "112001")


def test_all_quality_flags_retained_and_response_independence(tmp_path):
    e = entries()
    before = list(ppg.archive_records(save(tmp_path, e)))
    e["quality-hr-ann.csv"] = e["quality-hr-ann.csv"].replace(b",0,90", b",1,199")
    e["100001/100001_ECG.dat"] = b"changed held-out response bytes"
    after = list(ppg.archive_records(save(tmp_path, e)))
    assert len(before) == len(after) == 3
    assert [r[1] for r in before] != [r[1] for r in after]
    assert [ppg.signal_features(r[2]) for r in before] == [ppg.signal_features(r[2]) for r in after]
    assert all(r[3]["source_quality"] == 1 for r in after)


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "demographic",
        "motion",
        "missing_reference",
        "record_inventory",
        "publisher_hash",
    ],
)
def test_reject_ambiguous_identity_or_member(tmp_path, fault):
    e = entries()
    if fault == "duplicate":
        e["quality-hr-ann.csv"] += b"100001,0,90\r\n"
    elif fault == "demographic":
        e["subject-info.csv"] = e["subject-info.csv"].replace(b"100002,F,40", b"100002,F,41")
    elif fault == "motion":
        e["subject-info.csv"] = e["subject-info.csv"].replace(b"2;3", b"99")
    elif fault == "missing_reference":
        e["quality-hr-ann.csv"] = e["quality-hr-ann.csv"].replace(b",90", b",nan")
    elif fault == "record_inventory":
        e["RECORDS.txt"] += b"\n112001/112001_PPG"
    path = save(tmp_path, e)
    if fault == "publisher_hash":
        with zipfile.ZipFile(path) as z:
            all_entries = {n: z.read(n) for n in z.namelist()}
        all_entries[ppg.PREFIX + "100001/100001_PPG.dat"] = b"bad bytes"
        with zipfile.ZipFile(path, "w") as z:
            for n, b in all_entries.items():
                z.writestr(n, b)
    with pytest.raises(ValueError):
        list(ppg.archive_records(path))


def test_complete_person_splits_and_no_protected_target_exports(tmp_path, monkeypatch):
    signal = waveform()[2]

    def records(_):
        for person in range(100, 150):
            for row in range(77 if person < 112 else 78):
                yield (
                    f"{person}{row:03}",
                    90,
                    signal,
                    {"layout": "fixture", "source_quality": 0, "motion_code": "0", "ear_code": 1},
                )

    monkeypatch.setattr(ppg, "archive_records", records)
    path = tmp_path / "source.json"
    path.write_text(
        json.dumps(
            {
                "source_url": ppg.SOURCE_URL,
                "source_version": "2.0.0; 2024-08-23",
                "license_or_terms": "CC BY 4.0",
            }
        )
    )
    archive = tmp_path / "archive"
    archive.write_bytes(b"fixture")
    r = {
        "schema_version": "native-reconstruction/1",
        "parser": "ppg-native-waveform-features-v1",
        "scenario_id": "P100-033",
        "input_units": ppg.INPUT_UNITS,
        "output_units": "bpm",
        "group_assignments": ppg.original_assignments(
            "P100-033", [str(n) for n in range(100, 150)]
        ),
        "assets": [
            {"path": p.name, "sha256": file_sha(p), "bytes": p.stat().st_size, "role": role}
            for p, role in [(path, "source_metadata"), (archive, "ppg_archive")]
        ],
    }
    parts, lineage, checks = reconstruct(r, tmp_path)
    assert sum(map(len, parts.values())) == len(lineage) == 3888
    assert "source_quality" not in json.dumps(lineage)
    assert "motion_code" not in json.dumps(lineage)
    assert checks["split_check"]["valid"]
    assert {k: len({x["group"] for x in rows}) for k, rows in parts.items()} == {
        "train": 32,
        "dev": 8,
        "test": 10,
    }
    assert all("target" not in row for row in parts["test"])
    assert set(parts["test"][0]) == set(ppg.INPUT_UNITS) | {"sample_id", "group"}
    assert checks["ppg_validation"]["linear_detrend_fits"] == 3888
    r["group_assignments"]["119"] = "train"
    with pytest.raises(ValueError, match="allocation"):
        reconstruct(r, tmp_path)
    r["group_assignments"] = ppg.original_assignments("P100-033", [str(n) for n in range(100, 150)])
    archive.write_bytes(b"mutated")
    with pytest.raises(ValueError):
        reconstruct(r, tmp_path)
