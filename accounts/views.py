from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count

from cases.models import Case, Document, DocumentVersion
from .models import User
from cases.models import Case, Document, DocumentVersion


def login_view(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:

            if not user.is_active:
                return render(
                    request,
                    "accounts/login.html",
                    {
                        "error": "Your account is not active."
                    }
                )

            login(request, user)

            return redirect("dashboard")

        return render(
            request,
            "accounts/login.html",
            {
                "error": "Invalid username or password."
            }
        )

    return render(
        request,
        "accounts/login.html"
    )


def register_view(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":

        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        username = request.POST.get("username")
        email = request.POST.get("email")
        id_number = request.POST.get("id_number")
        phone_number = request.POST.get("phone_number")
        department = request.POST.get("department")
        designation = request.POST.get("designation")
        police_station = request.POST.get("police_station", "").strip()
        role = request.POST.get("role")

        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")

        # Password check
        if password1 != password2:
            return render(
                request,
                "accounts/register.html",
                {
                    "error": "Passwords do not match."
                }
            )

        # Username check
        if User.objects.filter(
            username=username
        ).exists():

            return render(
                request,
                "accounts/register.html",
                {
                    "error": "Username already exists."
                }
            )

        # ID check
        if User.objects.filter(
            id_number=id_number
        ).exists():

            return render(
                request,
                "accounts/register.html",
                {
                    "error": "Identification number already exists."
                }
            )

        # Create user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password1,
            first_name=first_name,
            last_name=last_name,
            id_number=id_number,
            phone_number=phone_number,
            department=department,
            designation=designation,
            police_station=police_station,
            role=role
        )

        # Login after registration
        login(request, user)

        return redirect("dashboard")

    return render(
        request,
        "accounts/register.html"
    )


def logout_view(request):

    logout(request)

    return redirect("login")

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from cases.models import Case, Document, DocumentVersion


@login_required
def dashboard(request):

    user = request.user

    # =========================================================
    # CASES VISIBLE / ASSIGNED TO CURRENT USER
    # =========================================================

    if user.role == "SHO":
        # SHO can see all cases
        user_cases = Case.objects.all()

    elif user.role == "IO":





        user_cases = Case.objects.filter(
            Q(created_by=user) |
            Q(assigned_to=user) |
            Q(assigned_officers=user)
        ).distinct()

    elif user.role == "FORENSIC_OFFICER":
        # Forensic officer sees only assigned/collaborating cases
        user_cases = Case.objects.filter(
            Q(assigned_to=user) |
            Q(assigned_officers=user)
        ).distinct()

    else:
        # Admin / other users
        user_cases = Case.objects.all()


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

    if user.role == "SHO":

        assigned_cases = Case.objects.all()

    else:

        assigned_cases = Case.objects.filter(
    Q(created_by=request.user)
    | Q(assigned_to=request.user)
    | Q(assigned_officers=request.user)
).select_related(
    "created_by",
    "assigned_to",
).prefetch_related(
    "assigned_officers",
).distinct().order_by("-updated_at")


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
        }
    )


