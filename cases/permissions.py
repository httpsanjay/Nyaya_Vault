from django.db.models import Q
from django.utils import timezone

from .models import Case, DocumentShare


def same_station(user, case):
    if not user.is_authenticated:
        return False
    return bool(
        user.police_station_id
        and user.police_station_id == case.police_station_id
    )


def can_access_case(user, case):
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.role == "ADMIN":
        return True
    if not same_station(user, case):
        return False
    if user.role == "SHO":
        return True
    if user.role in {"IO", "FORENSIC_OFFICER"}:
        return case.created_by_id == user.id or case.assigned_to_id == user.id or case.assigned_officers.filter(pk=user.pk).exists()
    return False


def active_share_queryset(user, version):
    now = timezone.now()
    shares = version.shares.filter(
        is_active=True,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    return shares.filter(
        Q(target_type=DocumentShare.POLICE_STATION, police_station_id=user.police_station_id)
        | Q(target_type__in=[DocumentShare.LAWYER, DocumentShare.COURT], recipient_user_id=user.id)
    )


def can_access_document_version(user, version):
    return can_access_case(user, version.document.case) or active_share_queryset(user, version).exists()


def can_download_document_version(user, version):
    if can_access_case(user, version.document.case):
        return True
    return active_share_queryset(user, version).filter(
        permission__in=[DocumentShare.DOWNLOAD, DocumentShare.VIEW_DOWNLOAD]
    ).exists()