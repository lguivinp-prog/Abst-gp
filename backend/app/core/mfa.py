"""
Servicio MFA TOTP (RFC 6238) para ABST-GP V6 (P14 Hardening).
Soporta enrolamiento en dos fases, validacion de ventanas de tiempo,
proteccion anti-replay de pasos exactos de 30 segundos y estados formales (P14-R1-05).
"""

import time
from typing import Optional, Tuple
import pyotp
from app.models.domain import MfaStatus


def generate_totp_secret() -> str:
    """Genera un secreto TOTP aleatorio de 32 caracteres en Base32."""
    return pyotp.random_base32()


def get_totp_provisioning_uri(secret: str, username: str, issuer: str = "ABST-GP V6") -> str:
    """Genera el URI otpauth:// estandar para lectores TOTP (Google Authenticator, Aegis, Bitwarden)."""
    totp = pyotp.TOTP(secret, interval=30)
    return totp.provisioning_uri(name=username, issuer_name=issuer)


def verify_totp_code(
    secret: str,
    code: str,
    last_verified_step: Optional[int] = None,
    current_timestamp: Optional[float] = None
) -> Tuple[bool, Optional[int], str]:
    """
    Verifica un codigo TOTP de 6 digitos frente al secreto en Base32.
    
    Aplica controles de seguridad estrictos (P14-R1-05):
    1. Formato exacto de 6 digitos numericos.
    2. Identificacion del paso temporal exacto coincidente dentro de la ventana [t-1, t, t+1].
    3. Proteccion anti-replay con monotonia estricta: matched_step > last_verified_step.
    
    Retorna: (is_valid, new_step, reason)
    """
    clean_code = str(code).strip()
    if not clean_code.isdigit() or len(clean_code) != 6:
        return False, None, "El codigo debe tener exactamente 6 digitos numericos."

    now = current_timestamp if current_timestamp is not None else time.time()
    current_step = int(now // 30)
    totp = pyotp.TOTP(secret, interval=30)

    # Identificar el paso exacto coincidente dentro de la ventana de tolerancia [-1, 0, +1]
    candidate_steps = [current_step - 1, current_step, current_step + 1]
    matched_step = None

    for step in candidate_steps:
        # valid_window=0 evalua unicamente el paso especificado en for_time
        if totp.verify(clean_code, for_time=int(step * 30), valid_window=0):
            matched_step = step
            break

    if matched_step is None:
        return False, None, "Codigo TOTP incorrecto o desfasado."

    # Proteccion Anti-Replay con monotonia estricta:
    # Impide reutilizar el mismo codigo o validar un codigo de un paso temporal anterior o igual
    if last_verified_step is not None and matched_step <= last_verified_step:
        return False, None, "Codigo TOTP ya utilizado o expirado (anti-replay)."

    return True, matched_step, "Codigo TOTP valido."
