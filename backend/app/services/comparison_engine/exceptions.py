class ComparisonDomainError(Exception):
    """Excepción base de negocio para el Comparison Engine."""
    pass

class ComparisonRunNotFound(ComparisonDomainError):
    """El ComparisonRun no existe en la base de datos."""
    pass

class ComparisonRunNotClaimed(ComparisonDomainError):
    """El ComparisonRun ya fue reclamado por otro worker o finalizó."""
    pass

class ComparisonInvalidState(ComparisonDomainError):
    """El estado del ComparisonRun no permite la operación."""
    pass

class ComparisonProcessingError(ComparisonDomainError):
    """Error interno durante el cálculo o persistencia de la comparación."""
    pass
