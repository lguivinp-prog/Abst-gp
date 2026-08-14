from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timezone

security = HTTPBearer()

SECRET_KEY = "v7_dev_mock_secret_key_do_not_use_in_prod"

class JWTValidatorInterface:
    def __init__(self):
        self.secret = SECRET_KEY

    def validate_token(self, token: str):
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
            if "exp" in payload:
                exp_date = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
                if datetime.now(timezone.utc) > exp_date:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
            if "tenant_id" not in payload:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing tenant_id claim")
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

validator = JWTValidatorInterface()

def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    return validator.validate_token(credentials.credentials)
