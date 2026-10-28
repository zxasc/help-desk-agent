from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest

from help_desk_agent.core import CURRENT_TIME
from help_desk_agent.tools import calculate_refund

CARD = "To the same card within 5 working days."
VOUCHER = "As a new voucher of the same value, never as money."

FULL_REFUND_PERCENT = 100
HALF_REFUND_PERCENT = 50
NO_REFUND_PERCENT = 0
NO_REFUND_EUR = 0.0

FULL_REFUND_MIN_HOURS = 48.0
HALF_REFUND_MIN_HOURS = 24.0
ONE_MINUTE = timedelta(minutes=1)
ONE_HOUR_AFTER_CW_1001_START = timedelta(hours=73)

# Values of the mock bookings in conftest.py
RENTAL_PRICE_EUR = 40.0
HALF_RENTAL_PRICE_EUR = 20.0
DEPOSIT_EUR = 50.0
HALF_EXPENSIVE_RENTAL_PRICE_EUR = 40.0
HIGH_DEPOSIT_EUR = 300.0
ODD_RENTAL_PRICE_EUR = Decimal("12.35")
CENT = Decimal("0.01")
ROUNDED_HALF_OF_ODD_RENTAL_PRICE_EUR = float(
    (ODD_RENTAL_PRICE_EUR * HALF_REFUND_PERCENT / FULL_REFUND_PERCENT).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
)

FULL_RENTAL_REFUND = {
    "rental_refund_percent": FULL_REFUND_PERCENT,
    "rental_refund_eur": RENTAL_PRICE_EUR,
    "booking_fee_refund_eur": NO_REFUND_EUR,
    "deposit_refund_eur": DEPOSIT_EUR,
    "total_refund_eur": RENTAL_PRICE_EUR + DEPOSIT_EUR,
}
HALF_RENTAL_REFUND = {
    "rental_refund_percent": HALF_REFUND_PERCENT,
    "rental_refund_eur": HALF_RENTAL_PRICE_EUR,
    "booking_fee_refund_eur": NO_REFUND_EUR,
    "deposit_refund_eur": DEPOSIT_EUR,
    "total_refund_eur": HALF_RENTAL_PRICE_EUR + DEPOSIT_EUR,
}
DEPOSIT_ONLY_REFUND = {
    "rental_refund_percent": NO_REFUND_PERCENT,
    "rental_refund_eur": NO_REFUND_EUR,
    "booking_fee_refund_eur": NO_REFUND_EUR,
    "deposit_refund_eur": DEPOSIT_EUR,
    "total_refund_eur": DEPOSIT_EUR,
}


@pytest.mark.parametrize(
    ("booking_id", "now", "expected"),
    [
        pytest.param(
            "CW-1001",
            CURRENT_TIME,
            FULL_RENTAL_REFUND,
            id="72h before start refunds full rental",
        ),
        pytest.param(
            "CW-2048",
            CURRENT_TIME,
            {**FULL_RENTAL_REFUND, "hours_before_start": FULL_REFUND_MIN_HOURS},
            id="exactly 48h before start refunds full rental",
        ),
        pytest.param(
            "CW-2048",
            CURRENT_TIME + ONE_MINUTE,
            HALF_RENTAL_REFUND,
            id="just under 48h before start refunds half rental",
        ),
        pytest.param(
            "CW-2030",
            CURRENT_TIME,
            {
                "rental_refund_percent": HALF_REFUND_PERCENT,
                "rental_refund_eur": HALF_EXPENSIVE_RENTAL_PRICE_EUR,
                "booking_fee_refund_eur": NO_REFUND_EUR,
                "deposit_refund_eur": HIGH_DEPOSIT_EUR,
                "total_refund_eur": HALF_EXPENSIVE_RENTAL_PRICE_EUR + HIGH_DEPOSIT_EUR,
            },
            id="30h before start refunds half rental",
        ),
        pytest.param(
            "CW-2024",
            CURRENT_TIME,
            {**HALF_RENTAL_REFUND, "hours_before_start": HALF_REFUND_MIN_HOURS},
            id="exactly 24h before start refunds half rental",
        ),
        pytest.param(
            "CW-2024",
            CURRENT_TIME + ONE_MINUTE,
            DEPOSIT_ONLY_REFUND,
            id="just under 24h before start refunds deposit only",
        ),
        pytest.param(
            "CW-2006",
            CURRENT_TIME,
            DEPOSIT_ONLY_REFUND,
            id="6h before start refunds deposit only",
        ),
        pytest.param(
            "CW-1001",
            CURRENT_TIME + ONE_HOUR_AFTER_CW_1001_START,
            DEPOSIT_ONLY_REFUND,
            id="after start refunds deposit only",
        ),
        pytest.param(
            "CW-2035",
            CURRENT_TIME,
            {
                "rental_refund_eur": ROUNDED_HALF_OF_ODD_RENTAL_PRICE_EUR,
                "total_refund_eur": ROUNDED_HALF_OF_ODD_RENTAL_PRICE_EUR + DEPOSIT_EUR,
            },
            id="half of 12.35 is rounded half up to cents",
        ),
        pytest.param(
            "CW-1001",
            CURRENT_TIME,
            {"refund_method": CARD},
            id="card payment is refunded to card",
        ),
        pytest.param(
            "CW-2099",
            CURRENT_TIME,
            {
                "refund_method": VOUCHER,
                "total_refund_eur": RENTAL_PRICE_EUR + DEPOSIT_EUR,
            },
            id="voucher payment is refunded as voucher",
        ),
    ],
)
def test_calculate_refund(booking_id, now, expected):
    result = calculate_refund(booking_id, now=now)

    assert {key: result[key] for key in expected} == expected


@pytest.mark.parametrize(
    ("booking_id", "expected"),
    [
        pytest.param(
            booking_id,
            {
                "booking_id": booking_id,
                "can_cancel": False,
                "reason": f"Bookings with status '{status}' cannot be cancelled "
                "and nothing is refunded.",
                "total_refund_eur": NO_REFUND_EUR,
            },
            id=f"{status} booking cannot be cancelled",
        )
        for booking_id, status in [
            ("CW-3001", "cancelled"),
            ("CW-3002", "completed"),
            ("CW-3003", "in_progress"),
        ]
    ]
    + [
        pytest.param(
            "CW-9999",
            {"found": False, "booking_id": "CW-9999", "error": "Booking not found."},
            id="unknown booking is not found",
        ),
    ],
)
def test_calculate_refund_without_refund(booking_id, expected):
    assert calculate_refund(booking_id) == expected
