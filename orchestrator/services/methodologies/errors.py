class MethodologyError(ValueError):
    """Base error for governed methodology profile resolution."""


class MissingMethodologyError(MethodologyError):
    """Raised when a methodology agent is provided without a methodology."""


class UnsupportedMethodologyError(MethodologyError):
    """Raised when the requested methodology is not supported by CLike."""


class UnsupportedMethodologyAgentError(MethodologyError):
    """Raised when the requested methodology agent is unknown."""


class MethodologyPhaseAgentError(MethodologyError):
    """Raised when a methodology agent is not allowed for the requested phase."""


class BmadSelectedSkillsMissingError(MethodologyError):
    """Raised when manifest-selected BMAD vendor skills are absent from runtime context."""


class ClikeSelectedCapabilitiesMissingError(MethodologyError):
    """Raised when REQ-selected CLike capabilities are absent from runtime context."""
