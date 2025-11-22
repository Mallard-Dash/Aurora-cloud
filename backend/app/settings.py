# settings.py - simple shared settings
import os
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-please-change")
ALGORITHM = os.environ.get("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
# placeholders
SessionLocal = None
User = None
