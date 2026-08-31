from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import AuditLog


@login_required
def audit_list(request):

    # ONLY ADMIN CAN ACCESS AUDIT LOGS

    if request.user.role != "ADMIN":
        from django.contrib import messages
        from django.shortcuts import redirect

        messages.error(
            request,
            "Only administrators can access audit logs."
        )

        return redirect("dashboard")

    logs = AuditLog.objects.select_related(
        "user",
        "case",
        "document",
        "document_version",
    ).all()

    return render(
        request,
        "audit/audit_list.html",
        {
            "logs": logs,
        }
    )