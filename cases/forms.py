from django import forms
from django.contrib.auth import get_user_model

from .models import Case, Document, DocumentVersion


class CaseForm(forms.ModelForm):

    class Meta:
        model = Case

        fields = [
            "case_number",
            "title",
            "case_type",
            "other_case_type",
            "description",
        ]

        widgets = {
            "case_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: FIR/2026/001",
                }
            ),

            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter case title",
                }
            ),

            "case_type": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "other_case_type": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Specify case type",
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                }
            ),
        }


class DocumentForm(forms.ModelForm):

    class Meta:
        model = Document

        fields = [
            "name",
            "document_type",
            "description",
        ]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: FIR Report",
                }
            ),

            "document_type": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Describe this document...",
                }
            ),
        }


class DocumentVersionForm(forms.ModelForm):

    class Meta:
        model = DocumentVersion

        fields = [
            "file",
        ]

        widgets = {
            "file": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                }
            ),
        }


User = get_user_model()


class CaseAssignmentForm(forms.ModelForm):

    assigned_officers = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(
            role__in=["IO", "SHO"]
        ),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = Case
        fields = ["assigned_officers"]