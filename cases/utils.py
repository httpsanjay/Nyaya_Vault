import base64
import hashlib

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
        password=None
    )


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

def create_signature(file, private_key):

    private_key = load_private_key(
        private_key
    )

    file.seek(0)

    file_data = file.read()

    file.seek(0)

    signature = private_key.sign(

        file_data,

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


# ============================================================
# VERIFY DIGITAL SIGNATURE
# ============================================================

def verify_signature(
    file,
    signature,
    public_key
):

    try:

        public_key = load_public_key(
            public_key
        )

        file.seek(0)

        file_data = file.read()

        file.seek(0)

        signature_bytes = base64.b64decode(
            signature
        )

        public_key.verify(

            signature_bytes,

            file_data,

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

        try:
            file.seek(0)
        except Exception:
            pass

        return False


# ============================================================
# GENERATE RSA KEY PAIR
# ============================================================

def generate_user_keys():

    private_key = rsa.generate_private_key(

        public_exponent=65537,

        key_size=2048
    )

    private_pem = private_key.private_bytes(

        encoding=serialization.Encoding.PEM,

        format=serialization.PrivateFormat.PKCS8,

        encryption_algorithm=
        serialization.NoEncryption()
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