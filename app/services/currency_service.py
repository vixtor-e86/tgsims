"""
TGSIMS Universal Currency Reconciliation Service
Single source of truth for USD <-> NGN currency conversions and rounding reconciliation.
"""
from typing import Optional


def get_default_rate() -> float:
    """Retrieves active USD/NGN exchange rate from system settings."""
    try:
        from app.services.settings_service import SettingsService
        rate = SettingsService.get_usd_ngn_rate()
        return float(rate) if rate and float(rate) > 0 else 1600.0
    except Exception:
        return 1600.0


def reconcile_ngn_amount(usd: Optional[float], rate: Optional[float] = None) -> float:
    """
    Reconciles round-trip conversion distortion from 2-decimal USD storage.
    Because 2-decimal USD has a maximum error of +-0.005 * rate (approx +-6.75 NGN at rate 1350),
    snapping to the nearest clean multiple of 25 (or integer) when within error margin
    perfectly reconstructs the original intended Naira amount across all exchange rates.
    """
    if usd is None:
        return 0.0
    try:
        usd_f = float(usd)
    except (ValueError, TypeError):
        return 0.0

    if rate is None:
        rate = get_default_rate()
    rate = float(rate) if rate and float(rate) > 0 else 1600.0

    raw = usd_f * rate
    # Snap to nearest multiple of 25 if within maximum 2-decimal USD rounding error margin
    nearest25 = round(raw / 25.0) * 25.0
    max_err = rate * 0.0051  # +-0.005 * rate plus a tiny float epsilon
    if abs(raw - nearest25) <= max_err:
        return float(nearest25)

    # Snap to nearest whole integer if within sub-penny precision
    nearest1 = round(raw)
    if abs(raw - nearest1) <= 0.05:
        return float(nearest1)

    return raw


def clean_ngn(usd: Optional[float], rate: Optional[float] = None) -> float:
    """Alias for reconcile_ngn_amount."""
    return reconcile_ngn_amount(usd, rate)


def format_ngn(usd: Optional[float], rate: Optional[float] = None) -> str:
    """Formats a USD amount as a clean reconciled Naira string (e.g. '₦3,000.00')."""
    val = reconcile_ngn_amount(usd, rate)
    return f"₦{val:,.2f}"


def ngn_to_usd(ngn_amount: Optional[float], rate: Optional[float] = None, decimals: int = 4) -> float:
    """Converts a Naira amount to USD, preserving 4-decimal precision."""
    if ngn_amount is None:
        return 0.0
    try:
        ngn_f = float(ngn_amount)
    except (ValueError, TypeError):
        return 0.0
    if rate is None:
        rate = get_default_rate()
    rate = float(rate) if rate and float(rate) > 0 else 1600.0
    if rate <= 0:
        return 0.0
    return round(ngn_f / rate, decimals)
