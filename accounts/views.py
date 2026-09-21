from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from cases.models import Case, Document, DocumentVersion
from cases.models import Case, Document, DocumentVersion
from cases.models import DocumentShare
from .forms import RegistrationForm
from .models import User
from cases.models import Case, Document, DocumentVersion
from .forms import LoginForm

from django.http import JsonResponse
from django.contrib.auth import get_user_model

User = get_user_model()


def index_view(request):
    
    if request.user.is_authenticated:
        return redirect("dashboard")

    return render(request, "accounts/index.html")

def login_view(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)

        if form.is_valid():
            user = form.get_user()

            if not user.is_active:
                form.add_error(
                    None,
                    "Your account is not active."
                )
            else:
                login(request, user)
                return redirect("dashboard")

    else:
        form = LoginForm()

    return render(
        request,
        "accounts/login.html",
        {
            "form": form
        }
    )

def mcp_page(request):
    return render(
        request,
        "accounts/mcp_page.html"
    )


def register_view(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()

        # Login after registration
        login(request, user)

        return redirect("dashboard")

    return render(request, "accounts/register.html", {"form": form})





def check_unique_field(request):

    field = request.GET.get("field")
    value = request.GET.get("value", "").strip()

    allowed_fields = {
        "username": "username",
        "email": "email",
        "id_number": "id_number",
        "phone_number": "phone_number",
        "lawyer_registration_number": "lawyer_registration_number",
        "court_registration_number": "court_registration_number",
    }

    if field not in allowed_fields:
        return JsonResponse({
            "valid": False,
            "message": "Invalid field."
        })

    if not value:
        return JsonResponse({
            "valid": True,
            "message": ""
        })

    model_field = allowed_fields[field]

    exists = User.objects.filter(
        **{
            f"{model_field}__iexact": value
        }
    ).exists()

    if exists:
        return JsonResponse({
            "valid": False,
            "message": "Already exists."
        })

    return JsonResponse({
        "valid": True,
        "message": "Available."
    })


def logout_view(request):

    logout(request)

    return redirect("login")


@login_required
def dashboard(request):

    user = request.user

    # =========================================================
    # CASES VISIBLE / ASSIGNED TO CURRENT USER
    # =========================================================

    if user.role == "SHO":
        user_cases = Case.objects.filter(
            police_station=user.police_station,
        )

    elif user.role == "IO":





        user_cases = Case.objects.filter(
            police_station=user.police_station,
        ).filter(
            Q(created_by=user) |
            Q(assigned_to=user) |
            Q(assigned_officers=user)
        ).distinct()

    elif user.role == "FORENSIC_OFFICER":
        # Forensic officer sees only assigned/collaborating cases
        user_cases = Case.objects.filter(
            police_station=user.police_station,
        ).filter(
            Q(assigned_to=user) |
            Q(assigned_officers=user)
        ).distinct()

    else:
        # Admin / other users
        user_cases = Case.objects.all() if user.is_superuser or user.role == "ADMIN" else Case.objects.none()


    # =========================================================
    # STATISTICS
    # =========================================================

    total_cases = user_cases.count()

    total_documents = Document.objects.filter(
        case__in=user_cases
    ).count()

    pending_count = DocumentVersion.objects.filter(
        document__case__in=user_cases,
        status="PENDING_REVIEW"
    ).count()

    forensic_reports = Document.objects.filter(
        case__in=user_cases,
        document_type="FORENSIC_REPORT"
    ).count()


    # =========================================================
    # RECENT CASES
    # =========================================================

    recent_cases = user_cases.select_related(
        "created_by",
        "assigned_to"
    ).prefetch_related(
        "assigned_officers"
    ).order_by("-updated_at")[:8]


    # =========================================================
    # CASES SPECIFICALLY ASSIGNED TO USER
    # =========================================================

    assigned_cases = user_cases.select_related(
        "created_by",
        "assigned_to",
    ).prefetch_related(
        "assigned_officers",
    ).order_by("-updated_at")

    shared_versions = DocumentVersion.objects.filter(
        shares__is_active=True,
    ).filter(
        Q(shares__expires_at__isnull=True) |
        Q(shares__expires_at__gt=timezone.now()),
    ).filter(
        Q(shares__target_type=DocumentShare.POLICE_STATION,
          shares__police_station=user.police_station) |
        Q(shares__recipient_user=user),
    ).select_related(
        "document",
        "document__case",
    ).distinct()


    # =========================================================
    # RETURN DASHBOARD
    # =========================================================

    return render(
        request,
        "accounts/dashboard.html",
        {
            "total_cases": total_cases,
            "total_documents": total_documents,
            "pending_count": pending_count,
            "forensic_reports": forensic_reports,

            "recent_cases": recent_cases,
            "assigned_cases": assigned_cases,
            "shared_versions": shared_versions,
        }
    )


