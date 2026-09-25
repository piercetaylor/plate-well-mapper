from platemap.wells import parse_well, usable_wells, well_name


def test_well_name():
    assert well_name("B", 7) == "B7"


def test_parse_well():
    assert parse_well("B7") == ("B", 7)


def test_usable_wells_full():
    wells = usable_wells(avoid_edges=False)
    assert len(wells) == 96
    assert wells[0] == "A1"
    assert wells[-1] == "H12"


def test_usable_wells_edge():
    wells = usable_wells(avoid_edges=True)
    assert len(wells) == 60
    assert wells[0] == "B2"
    assert wells[-1] == "G11"
