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
    Reconciles round-trip conversion distortion from USD storage to exact Naira amounts.
    - Clean dollar amounts ($1.00, $2.00, $0.50) retain their exact mathematical product (e.g. $2 @ 1340 = 2,680).
    - 4-decimal amounts (e.g. 2.2388 for 3,000 NGN, 3.7313 for 5,000 NGN) round to their exact integer.
    - Legacy 2-decimal amounts (e.g. 2.24, 2.25, 1.85) snap to clean multiples of 25.
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

    # 1. Exact USD amounts (e.g. $1.00, $2.00, $0.50, $2.50) are direct USD settings or fees.
    # For example, Reactivation Fee = $2.00 at rate 1340 is EXACTLY 2680.0 NGN (never snapped to 2675).
    is_clean_usd = abs(usd_f * 2 - round(usd_f * 2)) < 1e-4
    if is_clean_usd:
        return float(round(raw))

    # 2. If usd was stored with sub-cent precision (4 decimals):
    # E.g. 2.2388 for 3000 NGN, 3.7313 for 5000 NGN.
    is_sub_cent = abs(round(usd_f, 2) - round(usd_f, 4)) > 1e-5
    if is_sub_cent:
        return float(round(raw))

    # 3. For legacy 2-decimal USD amounts with +-0.005 rounding error:
    nearest25 = round(raw / 25.0) * 25.0
    max_err = rate * 0.0051
    if abs(raw - nearest25) <= max_err:
        return float(nearest25)

    return float(round(raw))


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
