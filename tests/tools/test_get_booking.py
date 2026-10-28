import json

import pytest

from help_desk_agent.tools import get_booking, load_bookings

EXISTING_BOOKING_ID = "CW-1001"
UNKNOWN_BOOKING_ID = "CW-9999"
NOT_FOUND = "Booking not found."


@pytest.mark.parametrize(
    "booking_id",
    [
        pytest.param(EXISTING_BOOKING_ID, id="exact booking number"),
        pytest.param(EXISTING_BOOKING_ID.lower(), id="lowercase booking number"),
        pytest.param(
            f"  {EXISTING_BOOKING_ID} ", id="booking number with surrounding spaces"
        ),
        pytest.param(
            EXISTING_BOOKING_ID.removeprefix("CW-"),
            id="booking number without CW prefix",
        ),
    ],
)
def test_get_booking_returns_booking(booking_id, mock_bookings):
    expected = {"found": True, "booking": mock_bookings[EXISTING_BOOKING_ID]}

    assert get_booking(booking_id) == expected


@pytest.mark.parametrize(
    ("booking_id", "expected"),
    [
        pytest.param(
            UNKNOWN_BOOKING_ID,
            {"found": False, "booking_id": UNKNOWN_BOOKING_ID, "error": NOT_FOUND},
            id="unknown booking number",
        ),
        pytest.param(
            "",
            {"found": False, "booking_id": "", "error": NOT_FOUND},
            id="empty booking number",
        ),
        pytest.param(
            "hello",
            {"found": False, "booking_id": "HELLO", "error": NOT_FOUND},
            id="text that is not a booking number",
        ),
    ],
)
def test_get_booking_returns_not_found(booking_id, expected):

    assert get_booking(booking_id) == expected


def test_load_bookings_indexes_bookings_file_by_id(tmp_path):
    path = tmp_path / "bookings.json"
    path.write_text(json.dumps([{"id": "CW-1"}, {"id": "CW-2"}]))

    assert load_bookings(path) == {"CW-1": {"id": "CW-1"}, "CW-2": {"id": "CW-2"}}
