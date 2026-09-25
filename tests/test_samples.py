import pytest

from platemap.samples import PlatemapError, Sample, read_samples


def _write(tmp_path, text):
    path = tmp_path / "samples.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_read_samples_basic(tmp_path):
    path = _write(
        tmp_path,
        "sample_name,dilution_factor,notes\n"
        "Alpha,2,first\n"
        "Beta,,\n",
    )
    samples = read_samples(path)
    assert samples == [
        Sample(sample_name="Alpha", dilution_factor=2.0, notes="first"),
        Sample(sample_name="Beta", dilution_factor=1.0, notes=""),
    ]


def test_header_stripped_and_lowered(tmp_path):
    path = _write(tmp_path, " Sample_Name , Dilution_Factor \nAlpha,2\n")
    samples = read_samples(path)
    assert samples[0].sample_name == "Alpha"
    assert samples[0].dilution_factor == 2.0


def test_blank_rows_skipped(tmp_path):
    path = _write(tmp_path, "sample_name,dilution_factor,notes\nAlpha,1,\n,,\nBeta,1,\n")
    samples = read_samples(path)
    assert [s.sample_name for s in samples] == ["Alpha", "Beta"]


def test_duplicate_sample_name(tmp_path):
    path = _write(tmp_path, "sample_name\nAlpha\nAlpha\n")
    with pytest.raises(PlatemapError) as exc:
        read_samples(path)
    assert str(exc.value) == "duplicate sample_name 'Alpha' at lines 2 and 3"


def test_invalid_dilution_factor(tmp_path):
    path = _write(tmp_path, "sample_name,dilution_factor\nAlpha,abc\n")
    with pytest.raises(PlatemapError) as exc:
        read_samples(path)
    assert str(exc.value) == "invalid dilution_factor 'abc' at line 2"


def test_zero_or_negative_dilution_factor(tmp_path):
    path = _write(tmp_path, "sample_name,dilution_factor\nAlpha,0\n")
    with pytest.raises(PlatemapError):
        read_samples(path)


def test_missing_sample_name(tmp_path):
    path = _write(tmp_path, "sample_name,notes\n,hi\n")
    with pytest.raises(PlatemapError):
        read_samples(path)


def test_missing_required_column(tmp_path):
    path = _write(tmp_path, "notes\nhi\n")
    with pytest.raises(PlatemapError):
        read_samples(path)


def test_no_samples(tmp_path):
    path = _write(tmp_path, "sample_name\n")
    with pytest.raises(PlatemapError) as exc:
        read_samples(path)
    assert str(exc.value) == "no samples"


def test_trailing_commas_and_nonfinite_df(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("sample_name,dilution_factor\nAlpha,2,\n,,,\n", encoding="utf-8")
    assert [s.sample_name for s in read_samples(str(p))] == ["Alpha"]
    for bad in ("nan", "inf"):
        p.write_text(f"sample_name,dilution_factor\nAlpha,{bad}\n", encoding="utf-8")
        with pytest.raises(PlatemapError):
            read_samples(str(p))
