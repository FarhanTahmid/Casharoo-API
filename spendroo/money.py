"""
Money is stored as integer minor units (paisa, cents) plus an ISO 4217 code.
Floats never touch an amount.
"""
from decimal import Decimal
from rest_framework import serializers

# Minor-unit exponents that differ from the usual 2
CURRENCY_EXPONENTS = {
    'BIF': 0, 'CLP': 0, 'DJF': 0, 'GNF': 0, 'ISK': 0, 'JPY': 0, 'KMF': 0, 'KRW': 0,
    'PYG': 0, 'RWF': 0, 'UGX': 0, 'VND': 0, 'VUV': 0, 'XAF': 0, 'XOF': 0, 'XPF': 0,
    'BHD': 3, 'IQD': 3, 'JOD': 3, 'KWD': 3, 'LYD': 3, 'OMR': 3, 'TND': 3,
}
DEFAULT_EXPONENT = 2


def currency_exponent(currency):
    return CURRENCY_EXPONENTS.get(currency, DEFAULT_EXPONENT)


def to_major(amount_minor, currency):
    """Minor units to a Decimal in major units (12345, 'BDT') -> Decimal('123.45')."""
    return Decimal(amount_minor).scaleb(-currency_exponent(currency))


def format_money(amount_minor, currency):
    """Human-readable amount for reports: 'BDT 1,234.50'."""
    return f"{currency} {to_major(amount_minor, currency):,.{currency_exponent(currency)}f}"


def validate_currency(value):
    value = (value or '').upper()
    if len(value) != 3 or not value.isalpha():
        raise serializers.ValidationError('Currency must be a 3-letter ISO 4217 code.')
    return value
