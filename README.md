# NyayaVault

NyayaVault is a Django-based secure digital document management system for legal and investigation documents. It organizes documents around cases and provides controlled access, version tracking, review, signing, search, and audit records to help users manage case information consistently.

## Overview

Legal and investigation work often involves many files, versions, reviewers, and participating organizations. Keeping those records organized, knowing who can access them, and identifying whether a file has changed can be difficult when documents are managed separately.

NyayaVault groups documents under a case. Users can create cases, upload document versions, review their status, search available case information, and share selected versions with controlled permissions. Role-based access limits case visibility according to the user's role, police station, assignment, and active shares.

Each document version can store extracted text and a SHA-256 file hash. Review and signing data records important actions, while audit logs record events such as uploads, approvals, signatures, verification, sharing, and downloads.

## Key Features

- Case management with case numbers, types, descriptions, assignments, and status values
- Role-based access control for administrators, police roles, lawyers, and court officials
- Case-linked document and document-version management
- Document versioning without silently replacing earlier versions
- Document status and review workflow: draft, pending review, rejected, approved, and signed
- OCR/text extraction for supported PDF and image files through a background task
- SHA-256 file hashing when a document version is saved
- RSA digital signatures using an SHO-specific signing key
- Audit logging for important case and document actions, including the request IP address when available
- Authenticated document viewing and downloads with access checks
- Search across authorized cases, document metadata, and extracted text
- Controlled document sharing with view/download permissions, optional expiry, and revocation

The repository does not currently include RAG, LLM, MCP, or vector-database integration as a required feature. The search module can optionally use `sentence-transformers` if that package and model are installed, but it is not included in the current `requirements.txt`.

## User Roles

The application defines these roles:

- **IO (Investigating Officer):** Creates cases and works with cases created by, assigned to, or involving the officer.
- **SHO (Station House Officer):** Oversees cases associated with the SHO's police station and can use the digital-signing workflow.
- **Forensic Officer:** Works with cases where the officer is assigned or listed as a collaborating officer.
- **Lawyer:** Can receive documents through an active share addressed to that lawyer.
- **Court:** Can receive documents through an active share addressed to that court official.

The system also defines **System Administrator** and Django superuser access. Access depends on role, station, assignment, and active shares.

## Document Workflow

1. An authorized IO creates or selects a case.
2. A document is created and associated with the case.
3. A document version is uploaded and tracked with its version number.
4. OCR/text extraction may run as a Celery background task for supported PDF and image files.
5. The version can move through draft, review, rejection, and approval states.
6. An authorized SHO can enable digital signing and sign an approved document version.
7. The file hash, signature information, and audit records can be used to check integrity and review important actions.
8. Approved or signed documents can be viewed, downloaded, or shared when the user's permissions allow it.

## Security and Integrity

### Authentication and Authorization

Users authenticate through Django's session-based authentication. Passwords are handled through Django's authentication system. Access checks use the user's role, police station, case ownership or assignment, and active document shares. Shared documents can be limited to viewing or downloading and can have an expiry time or be revoked.

Their effectiveness depends on correct deployment configuration, protected secrets, and appropriate account administration.

### File Integrity

When a file is saved, NyayaVault calculates a SHA-256 hash from its contents and stores the hexadecimal result with the document version. If the file contents change, the calculated hash changes. Comparing hashes can therefore help detect an unauthorized or unexpected modification.

### Digital Signatures

Digital signing uses RSA through the Python `cryptography` package. The signature payload includes the document ID, version number, file hash, and SHO user ID. The payload is signed with the SHO's encrypted private key and can be verified with the corresponding public key.

A digital signature helps verify the signed content and the corresponding signing key. It does not provide confidentiality or encrypt the document contents.

### Transport Security

For non-debug deployments, the settings enable HTTPS redirection and secure session/CSRF cookies, and Render is configured with an HTTPS hostname. HTTPS/TLS protects data while it is being transmitted. Uploaded documents are stored using Django's file storage configuration; the project does not document or implement encryption at rest for those files.

## Search and OCR

The search page and JSON search endpoint search authorized case and document information. Search can match case metadata, document metadata, and extracted document text. The implementation includes keyword matching and an optional semantic matching path that uses `sentence-transformers` when available; otherwise it falls back to term-overlap scoring.

OCR/text extraction is queued through Celery and currently uses `pytesseract`, `pdf2image`, and Pillow. PDF pages and image files are processed when the required local OCR and PDF-rendering dependencies are available. OCR accuracy depends on document quality and format. Some scanned images or unsupported files may produce no usable extracted text, which limits text-based search.

## Technology Stack

| Layer | Technology |
|------|------------|
| Backend | Django 6.1 |
| API/JSON layer | Django REST Framework is installed; the application also exposes a Django JSON search endpoint |
| Database | SQLite by default in the current settings; PostgreSQL driver and a Render PostgreSQL resource are configured for deployment work |
| Cache/Queue | Redis |
| Background Tasks | Celery |
| Document Processing | Tesseract OCR, `pdf2image`, Pillow, and text extraction |
| Digital Signature | Python `cryptography` with RSA |
| Hashing | SHA-256 |
| Frontend | Django Templates, HTML, CSS, and JavaScript |
| Static Files | WhiteNoise in non-debug deployments |
| Deployment | Render configuration in `render.yaml` |

## Project Structure

```text
nyaya_vault/
├── accounts/
│   ├── models.py
│   ├── views.py
│   ├── forms.py
│   └── templates/accounts/
├── cases/
│   ├── models.py
│   ├── views.py
│   ├── permissions.py
│   ├── search.py
│   ├── ocr.py
│   ├── tasks.py
│   └── management/commands/
├── audit/
│   ├── models.py
│   ├── views.py
│   └── utils.py
├── nyaya_vault/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── static/
├── templates/
├── media/
├── manage.py
├── requirements.txt
├── build.sh
├── render.yaml
└── README.md
```

- `accounts` contains the custom user model, authentication, dashboard, and account routes.
- `cases` contains case, document, access, search, OCR, sharing, and signing workflows.
- `audit` contains the audit-log model and view.
- `nyaya_vault` contains project settings and root URLs.

## Installation

### Windows PowerShell

```powershell
git clone <repository-url>
cd sih
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create a `.env` file in the project root using the placeholders in [Environment Variables](#environment-variables). Do not commit this file.

The current settings use SQLite by default. For PostgreSQL, configure the project settings and connection details before migrations. Redis is required for the Celery OCR queue, and Tesseract plus the PDF rendering tools used by `pdf2image` are required for OCR.

Run the database setup and development server:

```powershell
python manage.py migrate
python manage.py seed_police_stations
python manage.py createsuperuser
python manage.py runserver
```

Start Redis separately when needed. Start a Celery worker from the project root in another terminal:

```powershell
celery -A nyaya_vault worker --loglevel=info
```

On Linux/macOS, activate the environment with `source .venv/bin/activate` and use the equivalent commands. The repository's `build.sh` installs dependencies, collects static files, runs migrations, and seeds police stations for deployment.

## Environment Variables

Example `.env` values:

```dotenv
SECRET_KEY=your-secret-key
DEBUG=False
SIGNING_KEY_ENCRYPTION_PASSWORD=your-password
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0
MEDIA_ROOT=media
SESSION_COOKIE_AGE=1209600
SESSION_EXPIRE_AT_BROWSER_CLOSE=False
```

`SECRET_KEY` and `SIGNING_KEY_ENCRYPTION_PASSWORD` are required by the application. Render also defines `DATABASE_URL` and generates `SECRET_KEY`, but the current settings file uses SQLite unless database configuration is updated. Never commit real credentials, database URLs, API keys, passwords, or private signing keys to GitHub.

## API

The project includes Django REST Framework and a user serializer, but it does not currently expose a broad DRF viewset or router-based API.

The implemented JSON search endpoint is:

```text
GET /cases/api/search/?q=<search-term>
```

It requires authentication and returns the query plus authorized, case-grouped search results. The main application is otherwise served through Django template views. Representative web routes include `/login/`, `/register/`, `/dashboard/`, `/cases/`, `/cases/search/`, and `/audit/`.

## Deployment

`render.yaml` defines a Render Python web service with `build.sh`, an ASGI Gunicorn start command, a free Render PostgreSQL resource, and a `SIGNING_KEY_ENCRYPTION_PASSWORD` value that must be supplied separately. The build script installs dependencies, collects static files, applies migrations, and seeds police stations.

Before deployment, configure PostgreSQL, provide the required environment variables, and ensure Redis is available for Celery OCR. Static files are collected during the build and served through WhiteNoise. The current Render file defines the web service but not a Celery worker service.

## Limitations

- OCR accuracy depends on document quality, language, layout, and supported format.
- Some scanned or unsupported documents may not produce extractable text.
- Search results are limited when a document has no extracted text.
- Optional semantic search depends on an extra package and model that are not in the current requirements file.
- Security depends on correct deployment configuration, secret management, user administration, and access-permission setup.
- Uploaded files are not documented as encrypted at rest.
- The default local database is SQLite, and the current settings require configuration changes to use the PostgreSQL resource declared for Render.
- Free hosting services may have resource, storage, worker, and availability limitations.

## Future Improvements

The following are planned or possible future improvements, not current required features:

- RAG-based case document analysis
- LLM-assisted case summarization
- Contradiction and missing-information detection
- MCP integration for controlled AI access to case information
- Vector database integration and improved semantic search
- Stronger document encryption at rest
- Integration with external legal or investigation systems
- Improved OCR for scanned documents
- Cloud storage integration
- Interoperability with standardized legal document formats

## Security Notice

Store secrets in environment variables and protect private signing keys. Enable HTTPS in deployment, configure access permissions carefully, and review user roles before using the system. NyayaVault is an academic/project implementation and should be properly reviewed, tested, and hardened before use with real confidential legal records.

## License

License information has not yet been specified.

## Author

Sri Sanjay K  
B.Tech CSE Student  
CMR University
