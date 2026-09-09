
from django.core.management.base import BaseCommand
from cases.models import PoliceStation


class Command(BaseCommand):
    help = "Seed default police stations"

    def handle(self, *args, **options):
        stations = [
            ("Banaswadi Police Station", "BAN"),
            ("Kalyan Nagar Police Station", "KYN"),
            ("Ramamurthy Nagar Police Station", "RMN"),
            ("Indiranagar Police Station", "IND"),
            ("Whitefield Police Station", "WHF"),
        ]

        for name, code in stations:
            station, created = PoliceStation.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "is_active": True,
                },
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created: {name} ({code})"
                    )
                )
            else:
                self.stdout.write(
                    f"Already exists: {name} ({code})"
                )

        self.stdout.write(
            self.style.SUCCESS("Police station seeding completed.")
        )
