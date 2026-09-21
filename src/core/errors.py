"""Exception hierarchy.

One base class so a caller can catch everything this project raises without also
catching library errors. The four leaves correspond to the four ways the pipeline
is allowed to fail: bad configuration, a record that does not satisfy its
contract, evidence that cannot be verified, and a model provider that did not
answer usefully.

Note what is absent: there is no exception for "model output was almost valid".
Spec Section 29.12 forbids relaxing validation to make output pass, so a
near-miss raises ``ValidationError`` or ``EvidenceError`` like any other failure
and travels to the failure log and the review queue.
"""

from __future__ import annotations


class EngineError(Exception):
    """Base class for every error this project raises deliberately."""


class ConfigError(EngineError):
    """Configuration is missing, malformed, or internally inconsistent.

    Also raised when a stage needs a credential that is absent. Configuration
    *loading* never requires a secret (see ``core.config``); the stage that
    actually needs one raises this at the point of use.
    """


class ValidationError(EngineError):
    """A record does not satisfy its contract.

    Distinct from ``pydantic.ValidationError``: this wraps schema failures at
    the pipeline boundary so callers are not coupled to pydantic.
    """


class EvidenceError(ValidationError):
    """An evidence span does not verify against the raw text it claims.

    A subclass of ``ValidationError`` because fabricated or unverifiable evidence
    is a contract failure, not a separate category of problem. Callers that want
    to treat the two alike can, and callers that need to distinguish a fabricated
    quote from a malformed enum still can.
    """


class ProviderError(EngineError):
    """A model provider was unavailable, timed out, or returned unusable output.

    Never a research finding. Spec Section 17.18 requires this to be recorded as
    a ``DecisionTechnicalState`` and excluded from every metric, so that a
    provider outage can never present as ``out_of_scope``.
    """
