import django_filters

from django.db.models import Q

from .models import Case, Document


class CaseFilter(django_filters.FilterSet):

    q = django_filters.CharFilter(
        method="filter_search",
        label="Search"
    )

    status = django_filters.ChoiceFilter(
        choices=Case.STATUS_CHOICES
    )

    case_type = django_filters.ChoiceFilter(
        choices=Case.CASE_TYPE_CHOICES
    )

    assigned_officer = django_filters.CharFilter(
        method="filter_assigned_officer",
        label="Assigned Officer"
    )

    class Meta:
        model = Case

        fields = [
            "q",
            "status",
            "case_type",
            "assigned_officer",
        ]

    def filter_search(self, queryset, name, value):

        return queryset.filter(
            Q(case_number__icontains=value)
            | Q(title__icontains=value)
            | Q(description__icontains=value)
            | Q(case_type__icontains=value)

            | Q(assigned_to__username__icontains=value)
            | Q(assigned_to__first_name__icontains=value)
            | Q(assigned_to__last_name__icontains=value)

            | Q(assigned_officers__username__icontains=value)
            | Q(assigned_officers__first_name__icontains=value)
            | Q(assigned_officers__last_name__icontains=value)

            | Q(created_by__username__icontains=value)
            | Q(created_by__first_name__icontains=value)
            | Q(created_by__last_name__icontains=value)

        ).distinct()

    def filter_assigned_officer(
        self,
        queryset,
        name,
        value
    ):

        return queryset.filter(
            Q(assigned_to__username__icontains=value)
            | Q(assigned_to__first_name__icontains=value)
            | Q(assigned_to__last_name__icontains=value)
            | Q(assigned_officers__username__icontains=value)
            | Q(assigned_officers__first_name__icontains=value)
            | Q(assigned_officers__last_name__icontains=value)
        ).distinct()


class DocumentFilter(django_filters.FilterSet):

    q = django_filters.CharFilter(
        method="filter_search",
        label="Search"
    )

    document_type = django_filters.ChoiceFilter(
        choices=Document.DOCUMENT_TYPE_CHOICES
    )

    class Meta:
        model = Document

        fields = [
            "q",
            "document_type",
        ]

    def filter_search(self, queryset, name, value):

        return queryset.filter(
            Q(name__icontains=value)
            | Q(description__icontains=value)
            | Q(case__case_number__icontains=value)
            | Q(case__title__icontains=value)
            | Q(uploaded_by__username__icontains=value)
            | Q(uploaded_by__first_name__icontains=value)
            | Q(uploaded_by__last_name__icontains=value)
        ).distinct()