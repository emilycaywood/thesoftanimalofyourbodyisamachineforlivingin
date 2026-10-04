import math
from typing import Literal

import pytest
from calflab import units as u
from calflab.schema import P, ui_schema
from pydantic import BaseModel, ValidationError


def test_roundtrip_units():
    assert u.to_si(610, "mm") == pytest.approx(0.61)
    assert u.from_si(0.61, "mm") == pytest.approx(610)
    assert u.to_si(180, "deg") == pytest.approx(math.pi)
    assert u.to_si(7000, "g") == pytest.approx(7.0)
    assert u.to_si(30, "kg.cm") == pytest.approx(2.94, abs=0.01)
    assert u.to_si(60, "rpm") == pytest.approx(2 * math.pi)


def test_unknown_unit_is_an_error():
    with pytest.raises(ValueError, match="Unknown unit"):
        u.to_si(1, "furlong")


class Demo(BaseModel):
    length: float = P(100.0, unit="mm", ge=10, le=500, step=5, desc="A length.", group="Size")
    count: int = P(3, ge=1, le=9, desc="A count.")
    free: float = P(1.5, desc="No range.")
    on: bool = P(True, desc="A toggle.")
    mode: Literal["a", "b"] = P("a", desc="A choice.")
    pos: tuple[float, float, float] = P((0.0, 0.0, 0.0), unit="mm", desc="A point.")
    tint: str = P("#ff0000", ui="color", desc="A colour.")


def test_ui_schema_infers_widgets():
    fields = {f["name"]: f for f in ui_schema(Demo)["fields"]}
    assert fields["length"]["ui"] == "slider"
    assert fields["length"]["unit"] == "mm"
    assert (fields["length"]["min"], fields["length"]["max"], fields["length"]["step"]) == (10, 500, 5)
    assert fields["length"]["group"] == "Size"
    assert fields["count"]["type"] == "integer" and fields["count"]["ui"] == "slider"
    assert fields["free"]["ui"] == "number"
    assert fields["on"]["ui"] == "toggle"
    assert fields["mode"]["ui"] == "enum" and fields["mode"]["choices"] == ["a", "b"]
    assert fields["pos"]["ui"] == "vector3"
    assert fields["tint"]["ui"] == "color"
    assert all(f["description"] for f in fields.values())


def test_schema_ranges_validate():
    with pytest.raises(ValidationError):
        Demo(length=5)
