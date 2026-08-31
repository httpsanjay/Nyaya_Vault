from django.urls import path

from . import views

urlpatterns = [

    path(
        "",
        views.case_list,
        name="case_list"
    ),

    path(
        "create/",
        views.case_create,
        name="case_create"
    ),

    path(
        "<int:pk>/",
        views.case_detail,
        name="case_detail"
    ),

    path(
        "<int:pk>/documents/create/",
        views.document_create,
        name="document_create"
    ),

    path(
        "documents/<int:pk>/upload-version/",
        views.document_upload_version,
        name="document_upload_version"
    ),

    path(
        "documents/<int:pk>/",
        views.document_detail,
        name="document_detail"
    ),

    path(
        "documents/versions/<int:pk>/sign/",
        views.sign_document_version,
        name="sign_document_version"
    ),


    path(
        "digital-signing/enable/",
        views.enable_digital_signing,
        name="enable_digital_signing"
    ),

    path(
    "documents/versions/<int:pk>/submit/",
    views.submit_document_for_review,
    name="submit_document_for_review"
),

path(
    "documents/versions/<int:pk>/approve/",
    views.approve_document,
    name="approve_document"
),

path(
    "documents/versions/<int:pk>/reject/",
    views.reject_document,
    name="reject_document"
),

path(
    "documents/versions/<int:pk>/sign/",
    views.sign_document_version,
    name="sign_document_version",
),

path(
    "documents/versions/<int:pk>/verify/",
    views.verify_document_version,
    name="verify_document_version",
),
path(
    "case/<int:pk>/assign/",
    views.assign_case,
    name="assign_case"
),
path(
    "documents/<int:pk>/delete/",
    views.document_delete,
    name="document_delete"
),
path(
    "documents/versions/<int:pk>/delete/",
    views.document_version_delete,
    name="document_version_delete"
),
]