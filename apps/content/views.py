import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.content.forms import EditContentForm, GenerateContentForm, ProjectForm
from apps.content.models import ContentGeneration, Project
from apps.content.services import (
    check_project_limit,
    enqueue_generation,
    usage_summary,
)

logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    projects = request.user.projects.all()[:10]
    summary = usage_summary(request.user)
    recent = ContentGeneration.objects.filter(user=request.user).select_related("project")[:5]
    return render(
        request,
        "content/dashboard.html",
        {"projects": projects, "summary": summary, "recent": recent},
    )


# ─── Projects ───────────────────────────────────────────────────────────────

@login_required
def project_list(request):
    projects = request.user.projects.all()
    summary = usage_summary(request.user)
    return render(request, "content/project_list.html", {"projects": projects, "summary": summary})


@login_required
def project_create(request):
    ok, msg = check_project_limit(request.user)
    if not ok:
        messages.error(request, msg)
        return redirect("content:project_list")

    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.user = request.user
            project.save()
            messages.success(request, f'Project "{project.name}" created.')
            return redirect("content:project_detail", pk=project.pk)
    else:
        form = ProjectForm()
    return render(request, "content/project_form.html", {"form": form, "action": "Create"})


@login_required
def project_edit(request, pk):
    project = get_object_or_404(Project, pk=pk, user=request.user)
    if request.method == "POST":
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, "Project updated.")
            return redirect("content:project_detail", pk=pk)
    else:
        form = ProjectForm(instance=project)
    return render(request, "content/project_form.html", {"form": form, "action": "Edit", "project": project})


@login_required
def project_delete(request, pk):
    project = get_object_or_404(Project, pk=pk, user=request.user)
    if request.method == "POST":
        name = project.name
        project.delete()
        messages.success(request, f'Project "{name}" deleted.')
        return redirect("content:project_list")
    return render(request, "content/project_confirm_delete.html", {"project": project})


@login_required
def project_detail(request, pk):
    project = get_object_or_404(Project, pk=pk, user=request.user)
    generations = project.generations.all()
    summary = usage_summary(request.user)
    form = GenerateContentForm()
    return render(
        request,
        "content/project_detail.html",
        {"project": project, "generations": generations, "summary": summary, "form": form},
    )


# ─── Content Generation ──────────────────────────────────────────────────────

@login_required
@require_POST
def generate_content(request, pk):
    project = get_object_or_404(Project, pk=pk, user=request.user)
    form = GenerateContentForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid form submission.")
        return redirect("content:project_detail", pk=pk)

    try:
        gen = enqueue_generation(
            user=request.user,
            project=project,
            content_type=form.cleaned_data["content_type"],
            prompt_extra=form.cleaned_data.get("prompt_extra", ""),
        )
        messages.success(request, "Content generation started. It will be ready shortly.")
        return redirect("content:generation_detail", pk=gen.pk)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("content:project_detail", pk=pk)


@login_required
def generation_status(request, pk):
    """HTMX polling endpoint — returns JSON with current status."""
    gen = get_object_or_404(ContentGeneration, pk=pk, user=request.user)
    return JsonResponse(
        {
            "status": gen.status,
            "word_count": gen.word_count,
            "error_message": gen.error_message,
        }
    )


@login_required
def generation_detail(request, pk):
    gen = get_object_or_404(ContentGeneration, pk=pk, user=request.user)
    form = EditContentForm(initial={"result_text": gen.result_text})
    return render(request, "content/generation_detail.html", {"gen": gen, "form": form})


@login_required
@require_POST
def generation_save(request, pk):
    gen = get_object_or_404(ContentGeneration, pk=pk, user=request.user)
    form = EditContentForm(request.POST)
    if form.is_valid():
        gen.result_text = form.cleaned_data["result_text"]
        gen.word_count = len(gen.result_text.split())
        gen.save(update_fields=["result_text", "word_count", "updated_at"])
        messages.success(request, "Content saved.")
    return redirect("content:generation_detail", pk=pk)


@login_required
def generation_export_md(request, pk):
    gen = get_object_or_404(ContentGeneration, pk=pk, user=request.user)
    filename = f"generation_{pk}_{gen.content_type}.md"
    response = HttpResponse(gen.result_text, content_type="text/markdown")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def generation_export_pdf(request, pk):
    gen = get_object_or_404(ContentGeneration, pk=pk, user=request.user)
    from apps.content.tasks import export_pdf_task

    result = export_pdf_task.delay(gen.id, request.user.id)
    messages.info(request, "PDF export started. Refresh in a moment to download.")
    return redirect("content:generation_detail", pk=pk)


@login_required
def generation_history(request):
    generations = (
        ContentGeneration.objects.filter(user=request.user)
        .select_related("project")
        .order_by("-created_at")
    )
    return render(request, "content/generation_history.html", {"generations": generations})
