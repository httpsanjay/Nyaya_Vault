import base64
import hashlib

from django.conf import settings
from django.db import transaction
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


# ============================================================
# CALCULATE FILE SHA-256
# ============================================================

def calculate_file_hash(file):

    sha256 = hashlib.sha256()

    file.seek(0)

    for chunk in iter(
        lambda: file.read(8192),
        b""
    ):
        sha256.update(chunk)

    file.seek(0)

    return sha256.hexdigest()


# ============================================================
# LOAD PRIVATE KEY
# ============================================================

def load_private_key(private_key):

    if isinstance(private_key, str):

        private_key = private_key.encode("utf-8")

    return serialization.load_pem_private_key(
        private_key,
        password=_encryption_password()
    )


def _encryption_password():
    password = getattr(settings, "SIGNING_KEY_ENCRYPTION_PASSWORD", None)
    if not password:
        raise ValueError(
            "SIGNING_KEY_ENCRYPTION_PASSWORD is not configured."
        )
    return password.encode("utf-8")


# ============================================================
# LOAD PUBLIC KEY
# ============================================================

def load_public_key(public_key):

    if isinstance(public_key, str):

        public_key = public_key.encode("utf-8")

    return serialization.load_pem_public_key(
        public_key
    )


# ============================================================
# CREATE DIGITAL SIGNATURE
# ============================================================

def create_signature(payload, private_key):

    private_key = load_private_key(
        private_key
    )

    signature = private_key.sign(

        payload,

        padding.PSS(
            mgf=padding.MGF1(
                hashes.SHA256()
            ),
            salt_length=padding.PSS.MAX_LENGTH
        ),

        hashes.SHA256()
    )

    return base64.b64encode(
        signature
    ).decode("utf-8")


def build_signature_payload(document_id, version_number, file_hash, user_id):

    return (
        f"DOCUMENT:{document_id}|"
        f"VERSION:{version_number}|"
        f"HASH:{file_hash}|"
        f"SHO:{user_id}"
    ).encode("utf-8")


# ============================================================
# VERIFY DIGITAL SIGNATURE
# ============================================================

def verify_signature(
    payload,
    signature,
    public_key
):

    try:

        public_key = load_public_key(
            public_key
        )

        signature_bytes = base64.b64decode(signature, validate=True)

        public_key.verify(

            signature_bytes,

            payload,

            padding.PSS(
                mgf=padding.MGF1(
                    hashes.SHA256()
                ),
                salt_length=padding.PSS.MAX_LENGTH
            ),

            hashes.SHA256()
        )

        return True

    except Exception:
        return False


# ============================================================
# GENERATE RSA KEY PAIR
# ============================================================

def generate_user_keys():

    private_key = rsa.generate_private_key(

        public_exponent=65537,

        key_size=4096
    )

    private_pem = private_key.private_bytes(

        encoding=serialization.Encoding.PEM,

        format=serialization.PrivateFormat.PKCS8,

        encryption_algorithm=serialization.BestAvailableEncryption(
            _encryption_password()
        )
    )

    public_key = private_key.public_key()

    public_pem = public_key.public_bytes(

        encoding=serialization.Encoding.PEM,

        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return (

        private_pem.decode("utf-8"),

        public_pem.decode("utf-8")
    )


def create_signing_key_for_sho(user):
    """Create exactly one encrypted RSA-4096 key pair for an SHO."""

    from django.contrib.auth import get_user_model
    from .models import UserSigningKey

    # Make sure this is an authenticated user
    if not user or not user.is_authenticated:
        raise ValueError("Authenticated user required.")

    # Only SHO can have a signing key
    if user.role != "SHO":
        raise ValueError(
            "Only SHO users can enable digital signing."
        )

    User = get_user_model()

    with transaction.atomic():

        # Lock the actual User row
        locked_user = (
            User.objects
            .select_for_update()
            .get(pk=user.pk)
        )

        # Check whether this SHO already has a key
        existing_key = (
            UserSigningKey.objects
            .filter(user=locked_user)
            .first()
        )

        if existing_key:
            return existing_key, False

        # Generate a unique RSA-4096 key pair
        private_key, public_key = generate_user_keys()

        # Store the key specifically for this SHO
        signing_key = UserSigningKey.objects.create(
            user=locked_user,
            private_key=private_key,
            public_key=public_key,
        )

        return signing_key, True

