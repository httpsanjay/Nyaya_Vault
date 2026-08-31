from .models import AuditLog


def get_client_ip(request):

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")

    if forwarded:

        return forwarded.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


def create_audit_log(
    request,
    action,
    description,
    case=None,
    document=None,
    document_version=None,
):

    AuditLog.objects.create(

        user=request.user
        if request.user.is_authenticated
        else None,

        action=action,

        description=description,

        case=case,

        document=document,

        document_version=document_version,

        ip_address=get_client_ip(request),

    )