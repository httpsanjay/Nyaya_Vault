from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):

    ROLE_CHOICES = [
        ('ADMIN', 'System Administrator'),
        ('IO', 'Investigating Officer'),
        ('SHO', 'Station House Officer'),
        ('FORENSIC_OFFICER', 'Forensic Officer'),
        ('LAWYER', 'Lawyer'),
        ('COURT', 'Court Official'),
    ]

    role = models.CharField(max_length=20,choices=ROLE_CHOICES,default='IO')

    phone_number = models.CharField(max_length=15,blank=True)

    id_number = models.CharField(max_length=20,unique=True)

    department = models.CharField(max_length=100,blank=True)

    designation = models.CharField(max_length=100,blank=True)

    police_station_name = models.CharField(max_length=150, blank=True)

    lawyer_registration_number = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
    )

    court_registration_number = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
    )

    police_station = models.ForeignKey(
        "cases.PoliceStation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"