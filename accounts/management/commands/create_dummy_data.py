from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from cases.models import (
    Case,
    Document,
    DocumentVersion,
    PoliceStation,
)
from cases.utils import (
    create_signing_key_for_sho,
    load_private_key,
)


PASSWORD = "Test@12345"


STATIONS = [
    ("Banaswadi Police Station", "BANASWADI"),
    ("Basavanagudi Police Station", "BASAVANAGUDI"),
    ("Bengaluru North Police Station", "BENGALURU_NORTH"),
    ("Bengaluru City Police Station", "BENGALURU_CITY"),
]


POLICE_USERS = [
    (
        "banaswadi",
        "Banaswadi Police Station",
        "BANASWADI",
    ),
    (
        "basavanagudi",
        "Basavanagudi Police Station",
        "BASAVANAGUDI",
    ),
    (
        "bengaluru_north",
        "Bengaluru North Police Station",
        "BENGALURU_NORTH",
    ),
]


class Command(BaseCommand):

    help = "Create complete dummy data for NyayaVault testing."

    def handle(self, *args, **options):

        try:

            with transaction.atomic():

                stations = self.create_stations()

                users = self.create_users(stations)

                cases = self.create_cases(
                    stations,
                    users,
                )

                self.create_documents(
                    cases,
                    users,
                )

                self.create_lawyer_and_court()

        except Exception as exc:

            raise CommandError(
                f"Dummy data creation failed: {exc}"
            ) from exc

        self.print_summary()

    # ============================================================
    # POLICE STATIONS
    # ============================================================

    def create_stations(self):

        stations = {}

        for name, code in STATIONS:

            station, _ = PoliceStation.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "is_active": True,
                },
            )

            stations[name] = station

        return stations

    # ============================================================
    # POLICE USER
    # ============================================================

    def create_police_user(
        self,
        username,
        role,
        station,
    ):

        user, _ = User.objects.get_or_create(
            username=username,
            defaults={
                "id_number": username.upper(),
            },
        )

        user.role = role
        user.police_station = station
        user.police_station_name = station.name
        user.is_active = True

        user.set_password(PASSWORD)

        user.save()

        return user

    # ============================================================
    # USERS
    # ============================================================

    def create_users(self, stations):

        users = {}

        for (
            username,
            station_name,
            code,
        ) in POLICE_USERS:

            station = stations[station_name]

            # -----------------------------
            # IO
            # -----------------------------

            io = self.create_police_user(
                username=f"io_{username}",
                role="IO",
                station=station,
            )

            # -----------------------------
            # SHO
            # -----------------------------

            sho = self.create_police_user(
                username=f"sho_{username}",
                role="SHO",
                station=station,
            )

            # -----------------------------
            # SHO SIGNING KEY
            # -----------------------------

            key, created = create_signing_key_for_sho(
                sho
            )

            # Verify private key can actually
            # be decrypted using configured password.

            load_private_key(
                key.private_key
            )

            users[f"io_{username}"] = io
            users[f"sho_{username}"] = sho

        # ========================================================
        # ADMIN
        # ========================================================

        admin, _ = User.objects.get_or_create(
            username="admin",
            defaults={
                "id_number": "ADMIN-001",
            },
        )

        admin.role = "ADMIN"
        admin.is_staff = True
        admin.is_superuser = True
        admin.is_active = True

        admin.set_password(
            "Admin@12345"
        )

        admin.save()

        users["admin"] = admin

        return users

    # ============================================================
    # CASES
    # ============================================================

    def create_cases(
        self,
        stations,
        users,
    ):

        definitions = [

            (
                "CASE-BAN-001",
                "Banaswadi Test Investigation",
                "Banaswadi Police Station",
                "banaswadi",
            ),

            (
                "CASE-BAS-001",
                "Basavanagudi Test Investigation",
                "Basavanagudi Police Station",
                "basavanagudi",
            ),

        ]

        cases = {}

        for (
            case_number,
            title,
            station_name,
            username,
        ) in definitions:

            station = stations[
                station_name
            ]

            io = users[
                f"io_{username}"
            ]

            sho = users[
                f"sho_{username}"
            ]

            case, _ = Case.objects.update_or_create(

                case_number=case_number,

                defaults={

                    "title": title,

                    "case_type": "THEFT",

                    "description": (
                        "Dummy case created for "
                        "NyayaVault security and "
                        "collaboration testing."
                    ),

                    "created_by": io,

                    "assigned_to": sho,

                    "status": "OPEN",

                    "police_station": station,

                    "police_station_name": station.name,
                },
            )

            # SHO belongs to the case
            case.assigned_officers.set(
                [sho]
            )

            cases[case_number] = case

        return cases

    # ============================================================
    # DOCUMENTS
    # ============================================================

    def create_documents(
        self,
        cases,
        users,
    ):

        documents = [

            (
                "CASE-BAN-001",
                "Banaswadi FIR",
                "FIR",
                "banaswadi",
            ),

            (
                "CASE-BAN-001",
                "Banaswadi Evidence Report",
                "EVIDENCE",
                "banaswadi",
            ),

            (
                "CASE-BAS-001",
                "Basavanagudi FIR",
                "FIR",
                "basavanagudi",
            ),

            (
                "CASE-BAS-001",
                "Basavanagudi Investigation Report",
                "INVESTIGATION_REPORT",
                "basavanagudi",
            ),
        ]

        for (
            case_number,
            document_name,
            document_type,
            username,
        ) in documents:

            case = cases[
                case_number
            ]

            io = users[
                f"io_{username}"
            ]

            sho = users[
                f"sho_{username}"
            ]

            document, _ = Document.objects.update_or_create(

                case=case,

                name=document_name,

                defaults={
                    "document_type": document_type,
                    "uploaded_by": io,
                },
            )

            version, created = (
                DocumentVersion.objects.get_or_create(

                    document=document,

                    version_number=1,

                    defaults={
                        "uploaded_by": io,
                        "status": "PENDING_REVIEW",
                    },
                )
            )

            # Create file only if missing

            if not version.file:

                safe_name = (
                    document_name
                    .lower()
                    .replace(" ", "_")
                    .replace("/", "_")
                )

                version.file = SimpleUploadedFile(

                    f"{safe_name}.txt",

                    (
                        f"NyayaVault test document\n\n"
                        f"Case: {case.case_number}\n"
                        f"Document: {document_name}\n"
                        f"Uploaded by: {io.username}\n"
                        f"Police Station: {case.police_station.name}\n"
                    ).encode("utf-8"),
                )

                version.save()

    # ============================================================
    # LAWYER + COURT
    # ============================================================

    def create_lawyer_and_court(self):

        lawyer, _ = User.objects.get_or_create(
            username="lawyer_test",
            defaults={
                "id_number": "LAWYER-001",
            },
        )

        lawyer.role = "LAWYER"
        lawyer.registration_number = "LAW-REG-001"
        lawyer.is_active = True

        lawyer.set_password(
            PASSWORD
        )

        lawyer.save()

        court, _ = User.objects.get_or_create(
            username="court_test",
            defaults={
                "id_number": "COURT-001",
            },
        )

        court.role = "COURT"
        court.registration_number = "COURT-REG-001"
        court.is_active = True

        court.set_password(
            PASSWORD
        )

        court.save()

    # ============================================================
    # SUMMARY
    # ============================================================

    def print_summary(self):

        self.stdout.write(
            "\n" + "=" * 60
        )

        self.stdout.write(
            "NYAYAVAULT DUMMY DATA"
        )

        self.stdout.write(
            "=" * 60
        )

        self.stdout.write(
            "\nPOLICE STATIONS"
        )

        for (
            name,
            code,
        ) in STATIONS:

            self.stdout.write(
                f"  {name} ({code})"
            )

        self.stdout.write(
            "\nPOLICE USERS"
        )

        for (
            username,
            station,
            code,
        ) in POLICE_USERS:

            self.stdout.write(
                f"\n{station}"
            )

            self.stdout.write(
                f"\n  IO:"
            )

            self.stdout.write(
                f"\n    username: io_{username}"
            )

            self.stdout.write(
                f"\n    password: {PASSWORD}"
            )

            self.stdout.write(
                f"\n  SHO:"
            )

            self.stdout.write(
                f"\n    username: sho_{username}"
            )

            self.stdout.write(
                f"\n    password: {PASSWORD}"
            )

            self.stdout.write(
                f"\n    signing key: RSA-4096"
            )

        self.stdout.write(
            "\n\nLAWYER"
        )

        self.stdout.write(
            "\n  username: lawyer_test"
        )

        self.stdout.write(
            "\n  password: Test@12345"
        )

        self.stdout.write(
            "\n  registration: LAW-REG-001"
        )

        self.stdout.write(
            "\n\nCOURT"
        )

        self.stdout.write(
            "\n  username: court_test"
        )

        self.stdout.write(
            "\n  password: Test@12345"
        )

        self.stdout.write(
            "\n  registration: COURT-REG-001"
        )

        self.stdout.write(
            "\n\nADMIN"
        )

        self.stdout.write(
            "\n  username: admin"
        )

        self.stdout.write(
            "\n  password: Admin@12345"
        )

        self.stdout.write(
            "\n\nTEST CASES"
        )

        self.stdout.write(
            "\n  CASE-BAN-001 → Banaswadi"
        )

        self.stdout.write(
            "\n  CASE-BAS-001 → Basavanagudi"
        )

        self.stdout.write(
            "\n\nTESTING FLOW"
        )

        self.stdout.write(
            "\n  1. Login as Banaswadi IO"
        )

        self.stdout.write(
            "\n  2. Verify CASE-BAN-001 is visible"
        )

        self.stdout.write(
            "\n  3. Verify CASE-BAS-001 is NOT visible"
        )

        self.stdout.write(
            "\n  4. Login as Banaswadi SHO"
        )

        self.stdout.write(
            "\n  5. Verify CASE-BAN-001 is visible"
        )

        self.stdout.write(
            "\n  6. Verify CASE-BAS-001 is NOT visible"
        )

        self.stdout.write(
            "\n  7. Approve/sign Banaswadi documents"
        )

        self.stdout.write(
            "\n  8. Use SHARE from SHO"
        )

        self.stdout.write(
            "\n  9. Share selected documents to Basavanagudi"
        )

        self.stdout.write(
            "\n 10. Login as Basavanagudi SHO"
        )

        self.stdout.write(
            "\n 11. Verify shared documents"
        )

        self.stdout.write(
            "\n 12. Verify SHA-256 integrity"
        )

        self.stdout.write(
            "\n 13. Verify RSA digital signature"
        )

        self.stdout.write(
            "\n 14. Test lawyer sharing using LAW-REG-001"
        )

        self.stdout.write(
            "\n 15. Test court sharing using COURT-REG-001"
        )

        self.stdout.write(
            "\n" + "=" * 60
        )