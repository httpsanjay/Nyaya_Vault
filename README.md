# NyayaVault

### Secure Digital Document Management System for Legal & Investigation Documents

[![Python](https://img.shields.io/badge/Python-3.14-3776AB?style=for-the-badge\&logo=python\&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.x-092E20?style=for-the-badge\&logo=django\&logoColor=white)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-4169E1?style=for-the-badge\&logo=postgresql\&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-Queue%20%26%20Cache-DC382D?style=for-the-badge\&logo=redis\&logoColor=white)](https://redis.io/)
[![REST API](https://img.shields.io/badge/API-Django%20REST%20Framework-A30000?style=for-the-badge)](https://www.django-rest-framework.org/)
[![License](https://img.shields.io/badge/License-Educational-blue?style=for-the-badge)](#license)

**NyayaVault** is a secure web-based document management system designed for storing, managing, reviewing, and tracking legal and investigation documents.

The system connects documents with cases and authorized officers while maintaining document versions, audit records, file integrity, and digital signatures.

---

## Overview

Legal and investigation teams handle documents such as:

* FIRs
* Investigation reports
* Witness statements
* Charge sheets
* Evidence records
* Forensic reports
* Case-related documents

Managing these documents manually can make it difficult to track versions, verify file integrity, control access, and identify who approved a document.

**NyayaVault** provides a centralized system where documents are linked to cases and access is controlled based on the user's role and permissions.

---

## Key Features

### 🔐 Role-Based Access Control

Different users have different responsibilities within the system.

Supported roles include:

* **Investigation Officer (IO)**
* **Station House Officer (SHO)**
* **Forensic Officer**
* **Lawyer**
* **Court**

Access to cases and documents can be restricted according to the user's role and assigned permissions.

---

### 📁 Case-Based Document Management

Documents are organized around cases instead of being stored as isolated files.

Each case can contain multiple documents and document versions.

Example:

```text
Case
 ├── FIR
 ├── Investigation Report
 ├── Witness Statement
 ├── Evidence Document
 ├── Forensic Report
 └── Charge Sheet
```

This makes it easier to find and manage all documents related to a particular investigation.

---

### 📝 Document Versioning

NyayaVault keeps track of different versions of documents.

Instead of replacing the original document, a new version can be created.

This helps maintain a history of document changes and supports investigation traceability.

---

### 🔏 Digital Signatures

NyayaVault supports digital signing of approved documents.

The current signing workflow is designed around an **IO → SHO** approval process.

```text
Investigation Officer
        │
        │ Upload Document
        ▼
     Document
        │
        ▼
   SHO Review
        │
        │ Approve
        ▼
   Digital Signature
        │
        ▼
   Signed Document
```

The system uses:

* **RSA 4096-bit keys** for digital signatures
* **SHA-256** for document hashing

The hash helps detect changes to the file, while the digital signature provides cryptographic evidence that the document was signed using the corresponding signing key.

---

### 🧾 File Integrity

Each document version can have a cryptographic hash.

Example:

```text
Original File
     │
     ▼
 SHA-256 Hash
     │
     ▼
Stored with Document Version
```

If the file is modified later, its calculated hash will differ from the stored hash.

This provides a way to detect byte-level changes to a document.

---

### 🔍 Document Search

NyayaVault includes document and case search functionality.

The system can search using information such as:

* Case ID
* Document name
* Document description
* Extracted document text
* Relevant keywords

Semantic search functionality can also use document embeddings to retrieve relevant content based on meaning rather than only exact keyword matches.

---

### 📄 OCR Support

Scanned documents and images may not contain selectable text.

NyayaVault can process supported documents using OCR to extract text.

The extracted text can then be used for:

* Search
* Document analysis
* Future semantic retrieval
* AI-assisted features

OCR processing is handled asynchronously using a task queue.

---

### ⚡ Background Processing

Redis is used to support background processing for tasks such as document text extraction.

```text
User Upload
     │
     ▼
Django
     │
     ▼
Task Queue
     │
     ▼
Redis
     │
     ▼
Background Worker
     │
     ▼
OCR / Text Extraction
```

This prevents heavy document-processing operations from blocking the main web request.

---

### 📋 Audit Trail

Important actions can be recorded in the system to provide a history of activity.

Examples include:

* Document uploads
* Document changes
* Reviews
* Approvals
* Digital signing
* Access-related actions

The audit trail helps provide visibility into how documents are handled.

---

## Technology Stack

| Technology                  | Purpose                   |
| --------------------------- | ------------------------- |
| **Python**                  | Backend programming       |
| **Django**                  | Web application framework |
| **Django REST Framework**   | REST API                  |
| **PostgreSQL**              | Database                  |
| **Celery**                  | Background processing     |
| **HTML / CSS / JavaScript** | Frontend                  |
| **SHA-256**                 | File integrity hashing    |
| **RSA 4096**                | Digital signatures        |
| **OCR**                     | Text extraction           |
| **Sentence Transformers**   | Semantic embeddings       |
| **FastMCP**                 | MCP Integration           |
| **Git**                     | Version control           |

---

## System Architecture

```text
                         ┌──────────────────────┐
                         │       Browser        │
                         │   Web Application     │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │       Django         │
                         │    Application       │
                         └───────┬───────┬──────┘
                                 │       │
                 ┌───────────────┘       └───────────────┐
                 ▼                                       ▼
       ┌──────────────────┐                    ┌──────────────────┐
       │   PostgreSQL     │                    │      Redis       │
       │     Database     │                    │ Queue / Cache    │
       └──────────────────┘                    └────────┬─────────┘
                                                        │
                                                        ▼
                                              ┌──────────────────┐
                                              │ Background Tasks │
                                              │ OCR / Processing │
                                              └──────────────────┘

                         ┌──────────────────────┐
                         │ Document Processing  │
                         │ Hash / Signature /   │
                         │ Text Extraction      │
                         └──────────────────────┘
```

---

## Document Security Model

NyayaVault uses multiple layers to protect document integrity.

### 1. Access Control

Users are given permissions based on their roles and assignments.

### 2. File Hashing

SHA-256 is used to generate a cryptographic fingerprint of a document.

### 3. Digital Signature

Approved documents can be digitally signed using RSA-based cryptography.

### 4. Audit Records

Important document operations can be recorded for traceability.

### 5. HTTPS

When deployed with HTTPS, TLS protects communication between the user's browser and the application during transmission.

> Digital signatures and hashing help verify document integrity and authenticity. HTTPS protects the communication channel while data is being transmitted.

---

## Digital Signature Workflow

The signing process is designed to prevent unauthorized signing.

```text
IO uploads document
        │
        ▼
Document stored
        │
        ▼
SHO reviews document
        │
        ├── Reject ──► Document returned for changes
        │
        ▼
     Approve
        │
        ▼
SHO signs document
        │
        ▼
SHA-256 hash + RSA signature
        │
        ▼
Signed document version
```

The signature is associated with the approved document version.

---

## Project Structure

```text
nyaya_vault/
│
├── accounts/
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   └── templates/
│
├── cases/
│   ├── models.py
│   ├── views.py
│   ├── search.py
│   └── urls.py
│
├── audit/
│   ├── models.py
│   └── ...
│
├── nyaya_vault/
│   ├── settings.py
│   ├── urls.py
│   └── ...
│
├── static/
│   ├── css/
│   ├── js/
│   └── images/
│
├── templates/
│
├── manage.py
├── requirements.txt
└── README.md
```

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/httpsanjay/nyaya-vault.git
cd nyaya-vault
```

> Replace the repository URL with the actual repository URL if the repository name is different.

### 2. Create a Virtual Environment

Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

Linux / macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file.

Example:

```env
SECRET_KEY=DJANGO_SECRET_KEY
DEBUG=True or False
ALLOWED_HOSTS=localhost,127.0.0.1,*.localhost
SESSION_COOKIE_AGE=7200
SESSION_EXPIRE_AT_BROWSER_CLOSE=True or False
SIGNING_KEY_ENCRYPTION_PASSWORD=test-signing-password
MCP_AUTH_TOKEN=MCP_TOKEN
MCP_HOST=0.0.0.0
MCP_PORT=8001
```

### 5. Run Migrations

```bash
python manage.py migrate
```

### 6. Create an Administrator

```bash
python manage.py createsuperuser
```

### 7. Start the Development Server

```bash
python manage.py runserver
```

The application will normally be available at:

```text
http://127.0.0.1:8000/
```

---

## API

NyayaVault uses Django REST Framework for API-based operations.

The API can be used for application features such as:

* Authentication
* Case management
* Document management
* Document versions
* Search
* Case-related operations

API documentation can be exposed through the project's configured API documentation system.

---

## AI and Semantic Search

NyayaVault is designed to support AI-assisted document retrieval and analysis.

The semantic search pipeline can use:

```text
Document
    │
    ▼
Text Extraction
    │
    ▼
Text Chunking
    │
    ▼
Embeddings
    │
    ▼
Vector Search
    │
    ▼
Relevant Documents
```

A future RAG architecture can build on this retrieval layer.

### Planned AI Capabilities

* Case summarization
* Relevant document retrieval
* Question answering over authorized case documents
* Identification of missing information
* Contradiction detection
* Investigation document analysis

AI features should only operate on information that the authenticated user is authorized to access.

---

## MCP Integration

NyayaVault is also being extended with **Model Context Protocol (MCP)** integration.

The goal is to provide controlled access to application capabilities through defined MCP tools and prompts.

Possible operations include:

```text
User
 │
 ▼
AI Application
 │
 ▼
MCP
 │
 ├── Case Search
 ├── Document Search
 ├── Case Information
 └── Authorized Retrieval
        │
        ▼
    NyayaVault
```

MCP access must respect the application's existing authentication and authorization rules.

---

## Security Considerations

This project is designed as a security-focused academic and development project.

Important security areas include:

* Role-based access control
* Authentication
* Authorization
* File integrity verification
* Digital signatures
* Secure secret management
* HTTPS/TLS in deployment
* Audit logging
* Controlled document access
* Protection of private signing keys

For a real production legal system, additional security controls, compliance requirements, infrastructure hardening, key management, monitoring, backups, disaster recovery, and formal security testing would be required.

---

## Use Cases

### Police / Investigation

Investigating officers can manage documents related to assigned cases.

### Senior Officers

SHOs can review and approve documents submitted by authorized officers.

### Forensic Teams

Forensic reports and related documents can be associated with cases.

### Legal Teams

Authorized lawyers can access documents shared with them.

### Courts

Authorized court users can access documents made available for the relevant case.

---

## SDG Alignment

NyayaVault is related to:

### UN Sustainable Development Goal 16

**Peace, Justice and Strong Institutions**

The project focuses on improving digital document management, traceability, controlled access, and information handling for legal and investigation workflows.

---

## Future Improvements

Planned improvements include:

* Advanced RAG pipeline
* Vector database integration
* MCP-based AI workflows
* Improved OCR processing
* AI-assisted case summaries
* Contradiction detection
* Advanced audit analytics
* Cloud object storage
* Stronger key management
* Document encryption at rest
* Improved interoperability
* Security testing and penetration testing
* Production-grade monitoring
* Backup and disaster recovery

---

## Current Status

**NyayaVault is an academic project / prototype under active development.**

The project demonstrates the architecture and implementation of secure digital document management concepts including:

* Case management
* Role-based access
* Document versioning
* OCR
* Document hashing
* Digital signatures
* Audit tracking
* Semantic search
* Background processing
* MCP integration

It should **not** be considered a certified production system for handling real confidential legal or investigation data without additional security, compliance, and infrastructure work.

---

## Contributing

This project is currently developed primarily as an academic project.

If you want to contribute:

1. Fork the repository.
2. Create a feature branch.

```bash
git checkout -b feature/your-feature
```

3. Make your changes.
4. Test the changes.
5. Commit your work.

```bash
git commit -m "Add your feature"
```

6. Push the branch.

```bash
git push origin feature/your-feature
```

7. Open a Pull Request.

---

## License

This project is intended for **educational and academic purposes**.

Add an appropriate open-source license to the repository if you decide to distribute the project under one.

---

## Author

**Sri Sanjay K**

B.Tech Computer Science Engineering
CMR University

**Vinutha NJ**

B.Tech Computer Science Engineering
CMR University

**Yashaswini DN**

B.Tech Computer Science Engineering
CMR University

---

<p align="center">
  <strong>NyayaVault</strong><br>
  Secure. Traceable. Case-Centric.
</p>

<p align="center">
  Built for secure digital document management in legal and investigation workflows.
</p>
