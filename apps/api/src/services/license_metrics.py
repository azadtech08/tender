"""Prometheus metric definitions for the licensing subsystem."""

from __future__ import annotations

try:
    from prometheus_client import Counter, Gauge, Histogram
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

    class _Noop:
        def labels(self, **_): return self
        def inc(self, *_, **__): pass
        def set(self, *_, **__): pass
        def observe(self, *_, **__): pass
        def time(self): return self
        def __enter__(self): return self
        def __exit__(self, *_): pass

    def Counter(name, doc, labels=None): return _Noop()   # type: ignore[misc]
    def Gauge(name, doc): return _Noop()                  # type: ignore[misc]
    def Histogram(name, doc, buckets=None): return _Noop() # type: ignore[misc]

# ── activation / heartbeat counters ──────────────────────────────────────────

license_activations_total = Counter(
    "tenzo_license_activations_total",
    "License activation attempts, labeled by outcome",
    ["result"],
)

license_heartbeats_total = Counter(
    "tenzo_license_heartbeats_total",
    "License heartbeat attempts, labeled by outcome",
    ["result"],
)

# ── enforcement counters ──────────────────────────────────────────────────────

license_enforcement_checks_total = Counter(
    "tenzo_license_enforcement_checks_total",
    "Calls to require_valid_license / verify_license_token, labeled by mode and result",
    ["mode", "result"],
)

license_feature_denials_total = Counter(
    "tenzo_license_feature_denials_total",
    "LicenseGuard.require_feature() denials, labeled by plan and feature",
    ["plan", "feature"],
)

license_usage_limit_denials_total = Counter(
    "tenzo_license_usage_limit_denials_total",
    "LicenseGuard.check_and_increment() denials, labeled by counter name",
    ["counter", "plan"],
)

# ── gauges ────────────────────────────────────────────────────────────────────

license_active_licenses = Gauge(
    "tenzo_license_active_licenses",
    "Number of licenses currently in status=active (scraped periodically)",
)

license_revocation_cache_size = Gauge(
    "tenzo_license_revocation_cache_size",
    "Current cardinality of the Redis license:revoked set",
)

# ── duration histograms ───────────────────────────────────────────────────────

license_activation_duration_seconds = Histogram(
    "tenzo_license_activation_duration_seconds",
    "Wall-clock time for POST /api/license/activate",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

license_heartbeat_duration_seconds = Histogram(
    "tenzo_license_heartbeat_duration_seconds",
    "Wall-clock time for POST /api/license/heartbeat",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
