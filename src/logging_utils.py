from __future__ import annotations

import logging


def configure_logging(*, verbose: int = 0, quiet: int = 0) -> None:
    """
    Configure application logging.

    Levels:
    - default: INFO
    - -v: DEBUG
    - -vv: DEBUG (same, but allows you to extend later)
    - -q: WARNING
    - -qq: ERROR
    """
    # Base is INFO; verbosity pushes down to DEBUG, quiet pushes up to WARNING/ERROR.
    level = logging.INFO

    if verbose > 0:
        level = logging.DEBUG
    if quiet == 1:
        level = logging.WARNING
    elif quiet >= 2:
        level = logging.ERROR

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
