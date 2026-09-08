from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):

    ROLE_CHOICES = [
        ('IO', 'Investigating Officer'),
        ('SHO', 'Station House Officer'),
        ('FORENSIC_OFFICER', 'Forensic Officer'),
    ]

    role = models.CharField(max_length=20,choices=ROLE_CHOICES,default='IO')

    phone_number = models.CharField(max_length=15,blank=True)

    id_number = models.CharField(max_length=20,unique=True)

    department = models.CharField(max_length=100,blank=True)

    designation = models.CharField(max_length=100,blank=True)

    police_station = models.CharField(max_length=150, blank=True)

    station = models.ForeignKey(
        "cases.PoliceStation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"