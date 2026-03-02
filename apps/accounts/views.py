import logging
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .forms import RegisterForm, LoginForm

logger = logging.getLogger(__name__)


def landing(request):
    if request.user.is_authenticated:
        return redirect("content:dashboard")
    return render(request, "landing.html")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("content:dashboard")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome! Your account has been created.")
            logger.info("New user registered: %s", user.username)
            return redirect("content:dashboard")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("content:dashboard")
    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.GET.get("next", "content:dashboard")
            return redirect(next_url)
        messages.error(request, "Invalid username or password.")
    else:
        form = LoginForm()
    return render(request, "accounts/login.html", {"form": form})


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("accounts:landing")


@login_required
def profile_view(request):
    return render(request, "accounts/profile.html", {"user": request.user})
