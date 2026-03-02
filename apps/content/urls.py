from django.urls import path
from . import views

app_name = "content"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("projects/", views.project_list, name="project_list"),
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("projects/<int:pk>/edit/", views.project_edit, name="project_edit"),
    path("projects/<int:pk>/delete/", views.project_delete, name="project_delete"),
    path("projects/<int:pk>/generate/", views.generate_content, name="generate_content"),
    path("generations/", views.generation_history, name="generation_history"),
    path("generations/<int:pk>/", views.generation_detail, name="generation_detail"),
    path("generations/<int:pk>/status/", views.generation_status, name="generation_status"),
    path("generations/<int:pk>/save/", views.generation_save, name="generation_save"),
    path("generations/<int:pk>/export/md/", views.generation_export_md, name="generation_export_md"),
    path("generations/<int:pk>/export/pdf/", views.generation_export_pdf, name="generation_export_pdf"),
]
