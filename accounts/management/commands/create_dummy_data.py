from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from cases.models import Case, Document, DocumentVersion, PoliceStation
from cases.utils import create_signing_key_for_sho, load_private_key


STATIONS = [
    ("Banaswadi Police Station", "BANASWADI"),
    ("Basavanagudi Police Station", "BASAVANAGUDI"),
    ("Bengaluru North Police Station", "BENGALURU_NORTH"),
    ("Bengaluru City Police Station", "BENGALURU_CITY"),
]

STATION_USERS = [
    ("banaswadi", "Banaswadi Police Station", "BANASWADI"),
    ("basavanagudi", "Basavanagudi Police Station", "BASAVANAGUDI"),
    ("bengaluru_north", "Bengaluru North Police Station", "BENGALURU_NORTH"),
]


class Command(BaseCommand):
    help = "Create the local police-station and digital-signing test dataset."

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                stations = self._create_stations()
                users = self._create_users(stations)
                cases = self._create_cases(stations, users)
                self._create_test_document(cases["CASE-BAN-001"], users["io_banaswadi"], users["sho_banaswadi"])
        except Exception as exc:
            raise CommandError(f"Dummy data creation failed: {exc}") from exc

        key_count = User.objects.filter(role="SHO", signing_key__isnull=False).count()
        sho_count = User.objects.filter(role="SHO").count()
        io_count = User.objects.filter(role="IO").count()
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("DUMMY DATA CREATED")
        self.stdout.write("=" * 50)
        for username, station_name, _ in STATION_USERS:
            self.stdout.write(f"\n{station_name.upper()}")
            self.stdout.write(f"IO:\n    username: io_{username}\n    password: Test@12345")
            self.stdout.write(f"SHO:\n    username: sho_{username}\n    password: Test@12345\n    signing key: RSA-4096")
        self.stdout.write("\nBENGALURU CITY POLICE STATION\n    active: yes")
        self.stdout.write("\nADMIN:\n    username: admin\n    password: Admin@12345")
        self.stdout.write("\nTEST CASES:\n    CASE-BAN-001\n    CASE-BAS-001")
        self.stdout.write("\nSUMMARY")
        self.stdout.write(f"    police stations: {PoliceStation.objects.count()}")
        self.stdout.write(f"    IO users: {io_count}")
        self.stdout.write(f"    SHO users: {sho_count}")
        self.stdout.write(f"    signing keys: {key_count}")
        self.stdout.write(f"    test cases: {Case.objects.filter(case_number__in=['CASE-BAN-001', 'CASE-BAS-001']).count()}")
        self.stdout.write(f"    RSA-4096 key generation succeeded: {'yes' if key_count == 3 else 'no'}")

    def _create_stations(self):
        return {
            name: PoliceStation.objects.update_or_create(
                code=code,
                defaults={"name": name, "is_active": True},
            )[0]
            for name, code in STATIONS
        }

    def _user(self, username, role, station):
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={
                "id_number": username.upper(),
                "role": role,
                "police_station": station.name,
                "station": station,
                "is_active": True,
            },
        )
        user.role = role
        user.police_station = station.name
        user.station = station
        user.is_active = True
        user.set_password("Test@12345")
        user.save()
        return user

    def _create_users(self, stations):
        users = {}
        for username, station_name, _ in STATION_USERS:
            station = stations[station_name]
            users[f"io_{username}"] = self._user(f"io_{username}", "IO", station)
            sho = self._user(f"sho_{username}", "SHO", station)
            key, _ = create_signing_key_for_sho(sho)
            load_private_key(key.private_key)
            users[f"sho_{username}"] = sho

        admin, _ = User.objects.get_or_create(
            username="admin",
            defaults={"id_number": "ADMIN-1", "role": "IO"},
        )
        admin.role = "IO"
        admin.is_staff = True
        admin.is_superuser = True
        admin.is_active = True
        admin.set_password("Admin@12345")
        admin.save()
        users["admin"] = admin
        return users

    def _create_cases(self, stations, users):
        definitions = [
            ("CASE-BAN-001", "Banaswadi Test Investigation", "Banaswadi Police Station", "banaswadi"),
            ("CASE-BAS-001", "Basavanagudi Test Investigation", "Basavanagudi Police Station", "basavanagudi"),
        ]
        cases = {}
        for case_number, title, station_name, username in definitions:
            io = users[f"io_{username}"]
            sho = users[f"sho_{username}"]
            case, _ = Case.objects.update_or_create(
                case_number=case_number,
                defaults={
                    "title": title,
                    "case_type": "THEFT",
                    "created_by": io,
                    "assigned_to": sho,
                    "police_station": station_name,
                    "station": stations[station_name],
                    "status": "OPEN",
                },
            )
            case.assigned_officers.set([sho])
            cases[case_number] = case
        return cases

    def _create_test_document(self, case, io, sho):
        document, _ = Document.objects.update_or_create(
            case=case,
            name="Banaswadi Signing Test Document",
            defaults={"document_type": "EVIDENCE", "uploaded_by": io},
        )
        version, _ = DocumentVersion.objects.update_or_create(
            document=document,
            version_number=1,
            defaults={
                "uploaded_by": io,
                "status": "APPROVED",
                "reviewed_by": sho,
            },
        )
        if not version.file:
            version.file = SimpleUploadedFile(
                "banaswadi-signing-test.txt",
                b"NyayaVault Banaswadi digital signing test document.",
            )
            version.save()
