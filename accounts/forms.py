from django import forms

from cases.models import PoliceStation

from .models import User


from django import forms
from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Username",
        widget=forms.TextInput(attrs={
            "placeholder": "Enter username",
            "autocomplete": "username",
        })
    )

    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "placeholder": "Enter password",
            "autocomplete": "current-password",
        })
    )



class RegistrationForm(forms.ModelForm):

    password1 = forms.CharField(
        widget=forms.PasswordInput
    )

    password2 = forms.CharField(
        widget=forms.PasswordInput
    )

    station = forms.ModelChoiceField(
        queryset=PoliceStation.objects.none(),
        required=False,
    )

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "username",
            "email",
            "id_number",
            "phone_number",
            "department",
            "designation",
            "role",
            "station",
            "lawyer_registration_number",
            "court_registration_number",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["station"].queryset = (
            PoliceStation.objects
            .filter(is_active=True)
            .order_by("name")
        )

    def clean(self):
        cleaned = super().clean()

        role = cleaned.get("role")
        station = cleaned.get("station")

        # Police roles require station
        if role in {"IO", "SHO", "FORENSIC_OFFICER"} and station is None:
            self.add_error(
                "station",
                "Select an active police station."
            )

        # Lawyer requires registration number
        if role == "LAWYER" and not cleaned.get(
            "lawyer_registration_number"
        ):
            self.add_error(
                "lawyer_registration_number",
                "Registration number is required."
            )

        # Court requires registration number
        if role == "COURT" and not cleaned.get(
            "court_registration_number"
        ):
            self.add_error(
                "court_registration_number",
                "Court registration number is required."
            )

        # Password match
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error(
                "password2",
                "Passwords do not match."
            )

        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)

        user.set_password(
            self.cleaned_data["password1"]
        )

        station = self.cleaned_data.get("station")

        user.police_station = station
        user.police_station_name = (
            station.name if station else ""
        )

        if commit:
            user.save()

        return user

    