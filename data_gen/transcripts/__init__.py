"""Paired-turn transcript generation and review package."""

from .corpus import (  # noqa: F401
    build_manifest,
    coverage,
    generate_from_scenarios,
    main,
    make_transcript,
    review,
    validate_corpus,
    validate_transcript,
)

