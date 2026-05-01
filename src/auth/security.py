from passlib.context import CryptContext

# bcrypt alone limits passwords to 72 bytes; bcrypt_sha256 hashes first
# (no practical limit).
# Keep ``bcrypt`` so existing DB hashes still verify.
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated=["bcrypt"],
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
