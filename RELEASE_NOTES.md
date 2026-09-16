# 0.3.0 — first standalone preview package

Prepared 15 September 2026 from the latest local integration source.

Includes stop picker, automatic sensors, named groups, departures card, TfGM
bus/tram boards, schedule fallback, optional BODS context, options flow and
redacted diagnostics. GitHub metadata now uses the owner's confirmed account.

Validation: Python modules compile and both frontend scripts pass Node syntax
checks. All packaged JSON parses. A focused scan found no embedded credentials
or household server addresses. Full Home Assistant runtime tests have not been
run in this packaging session: the desktop has Python 3.11, not the compatible
Home Assistant test environment. Existing HA-dependent tests are included.

This package does not deploy to Home Assistant automatically. Install it as a
preview and use the README's troubleshooting and reporting guidance.
