"""
Modulo Criptografico para ABST-GP V6 (P14 Hardening).
Implementa:
1. Cifrado autenticado AEAD (AES-256-GCM) con versionado de ciphertext y key-id para rotacion (P14-R1-17).
2. Validacion estricta de entropia y longitud de claves de 256 bits (32 bytes).
3. Firma y verificacion de integridad HMAC-SHA256 para manifiestos de backup (P14-R1-11).
4. Hashing Bcrypt de codigos de rescate break-glass (rounds=12).
"""

import os
import base64
import hashlib
import hmac
import secrets
import math
from typing import List, Union, Optional, Dict
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import bcrypt


def calculate_shannon_entropy(data: bytes) -> float:
    """Calcula la entropia de Shannon de una secuencia de bytes en bits por byte (0 a 8)."""
    if not data:
        return 0.0
    entropy = 0.0
    length = len(data)
    frequencies = {}
    for b in data:
        frequencies[b] = frequencies.get(b, 0) + 1
    for count in frequencies.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def validate_and_parse_key(key: Union[str, bytes], key_name: str = "KEY", allow_test_defaults: Optional[bool] = None) -> bytes:
    """
    Valida y normaliza una clave criptografica de 256 bits (32 bytes).
    Soporta bytes raw, hex de 64 caracteres o Base64.
    Exige longitud exacta de 32 bytes y comprueba entropia minima.
    En APP_ENV=lan o production, NUNCA permite derivacion de defaults (P14-R2-14).
    """
    app_env = os.environ.get("APP_ENV", "development").lower()
    if allow_test_defaults is None:
        allow_test_defaults = False if app_env in ("lan", "production") else True

    raw: bytes
    if isinstance(key, str):
        key_str = key.strip()
        # Intentar parsear como hex si mide 64 caracteres
        if len(key_str) == 64:
            try:
                raw = bytes.fromhex(key_str)
            except ValueError:
                raw = key_str.encode("utf-8")
        elif len(key_str) == 44 and key_str.endswith("="):
            try:
                raw = base64.urlsafe_b64decode(key_str.encode("utf-8"))
            except Exception:
                raw = key_str.encode("utf-8")
        else:
            raw = key_str.encode("utf-8")
    else:
        raw = key

    # Asegurar exactamente 32 bytes
    if len(raw) != 32:
        if allow_test_defaults:
            # Derivacion controlada SOLO para entornos locales de desarrollo/test
            raw = hashlib.sha256(raw).digest()
        else:
            raise ValueError(
                f"Clave criptografica '{key_name}' invalida: debe tener exactamente 32 bytes (256 bits). "
                f"Longitud actual: {len(raw)} bytes."
            )

    # Validacion de entropia minima para evitar patrones repetitivos (ej. 'aaaa...' o '1234...')
    entropy = calculate_shannon_entropy(raw)
    if entropy < 3.0 and not allow_test_defaults:
        raise ValueError(
            f"Clave criptografica '{key_name}' insegura: entropia insuficiente ({entropy:.2f} < 3.0 bits/byte)."
        )

    return raw


def encrypt_aead(plaintext: str, key: Union[str, bytes], key_id: str = "v1") -> str:
    """
    Cifra un texto plano utilizando AES-256-GCM con un nonce aleatorio de 12 bytes.
    Retorna una cadena con versionado de formato:
    '{key_id}:{base64_urlsafe(nonce + ciphertext + tag)}'
    """
    key_bytes = validate_and_parse_key(key, "MFA/DATA_KEY")
    aesgcm = AESGCM(key_bytes)
    nonce = os.urandom(12) # Nonce de 96 bits recomendado para GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    payload_b64 = base64.urlsafe_b64encode(nonce + ciphertext).decode("utf-8")
    return f"{key_id}:{payload_b64}"


def decrypt_aead(
    encrypted_payload: str,
    key: Union[str, bytes],
    key_ring: Optional[Dict[str, Union[str, bytes]]] = None
) -> str:
    """
    Descifra un payload cifrado con AES-256-GCM.
    Soporta formato versionado '{key_id}:{payload_b64}' y formato legado sin versionado.
    Lanza ValueError si el descifrado o la autenticacion de integridad falla.
    """
    try:
        raw_key = key
        payload_to_decode = encrypted_payload

        # Parsear version/key_id si esta presente
        if ":" in encrypted_payload:
            parts = encrypted_payload.split(":", 1)
            key_id = parts[0]
            payload_to_decode = parts[1]
            if key_ring and key_id in key_ring:
                raw_key = key_ring[key_id]

        key_bytes = validate_and_parse_key(raw_key, "DECRYPT_KEY")
        data = base64.urlsafe_b64decode(payload_to_decode.encode("utf-8"))
        if len(data) < 28: # 12 bytes nonce + 16 bytes tag minimo
            raise ValueError("Payload cifrado corrupto o incompleto.")

        nonce = data[:12]
        ciphertext = data[12:]
        aesgcm = AESGCM(key_bytes)
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext_bytes.decode("utf-8")
    except Exception as e:
        raise ValueError(f"Fallo al descifrar secreto AEAD: {e}") from e


def sign_hmac_sha256(data: bytes, key: Union[str, bytes]) -> str:
    """Firma criptograficamente un bloque de datos mediante HMAC-SHA256."""
    key_bytes = validate_and_parse_key(key, "SIGNING_KEY")
    return hmac.new(key_bytes, data, hashlib.sha256).hexdigest()


def verify_hmac_sha256(data: bytes, signature_hex: str, key: Union[str, bytes]) -> bool:
    """Verifica en tiempo constante si la firma HMAC-SHA256 coincide exactamente."""
    try:
        expected_sig = sign_hmac_sha256(data, key)
        return hmac.compare_digest(expected_sig, signature_hex.strip().lower())
    except Exception:
        return False


def hash_recovery_code(code: str) -> str:
    """Genera un hash Bcrypt con 12 rondas de sal para un codigo de recuperacion de rescate."""
    clean_code = code.strip().replace("-", "").upper()
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(clean_code.encode("utf-8"), salt).decode("utf-8")


def verify_recovery_code(code: str, hashed: str) -> bool:
    """Verifica en tiempo seguro si un codigo de recuperacion coincide con el hash Bcrypt."""
    clean_code = code.strip().replace("-", "").upper()
    try:
        return bcrypt.checkpw(clean_code.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def generate_recovery_codes(count: int = 8) -> List[str]:
    """
    Genera codigos de rescate alfanumericos aleatorios de alta entropia.
    Formato: XXXX-XXXX-XXXX-XXXX (16 caracteres hexadecimales en mayusculas).
    """
    codes = []
    for _ in range(count):
        part1 = secrets.token_hex(2).upper()
        part2 = secrets.token_hex(2).upper()
        part3 = secrets.token_hex(2).upper()
        part4 = secrets.token_hex(2).upper()
        codes.append(f"{part1}-{part2}-{part3}-{part4}")
    return codes
