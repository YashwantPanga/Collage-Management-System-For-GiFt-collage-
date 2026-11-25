from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import LoginForm, ProfileForm, RegisterForm
from .utils import audit, client_ip, notify

MAX_ATTEMPTS, LOCK_SECONDS = 5, 15 * 60


def _next_url(request, default="cms:dashboard"):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure()):
        return nxt
    return default


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_next_url(request))
    form = LoginForm(request, request.POST or None)
    if request.method == "POST":
        key = f"login-fail:{client_ip(request)}:{request.POST.get('username', '').lower()}"
        if cache.get(key, 0) >= MAX_ATTEMPTS:
            messages.error(request, "Too many failed attempts. Please try again in 15 minutes.")
            return render(request, "accounts/login.html", {"form": form})
        if form.is_valid():
            cache.delete(key)
            login(request, form.user)
            if not form.cleaned_data.get("remember"):
                request.session.set_expiry(0)
            audit(request, "auth.login", form.user)
            messages.success(request, f"Welcome back, {form.user.display_name}!")
            return redirect(_next_url(request))
        cache.set(key, cache.get(key, 0) + 1, LOCK_SECONDS)
        audit(request, "auth.login_failed", request.POST.get("username", "")[:100])
    return render(request, "accounts/login.html", {"form": form})


def register_view(request):
    if request.user.is_authenticated:
        return redirect("cms:dashboard")
    form = RegisterForm(request.POST or None, initial={"role": request.GET.get("role", "student")})
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.role = form.cleaned_data["role"]
        user.email = form.cleaned_data["email"]
        user.phone = form.cleaned_data["phone"]
        user.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        audit(request, "auth.register", user, user.role)
        notify(user, "Welcome to GIFT Autonomous", "Your account has been created.", "/portal/", "success", email=True)
        messages.success(request, "Account created successfully.")
        if user.role == "student":
            return redirect(_next_url(request, "cms:apply"))
        if user.role == "recruiter":
            messages.info(request, "Add your company profile — the placement cell will approve it.")
            return redirect("cms:resource_add", "company")
        return redirect("cms:dashboard")
    return render(request, "accounts/register.html", {"form": form})


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        audit(request, "auth.logout", request.user)
    logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("website:home")


@login_required
def profile_view(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user, prefix="p")
    pwd_form = PasswordChangeForm(request.user, request.POST if "change_password" in request.POST else None, prefix="pw")
    if request.method == "POST":
        if "change_password" in request.POST:
            if pwd_form.is_valid():
                user = pwd_form.save()
                update_session_auth_hash(request, user)
                audit(request, "auth.password_change", user)
                messages.success(request, "Password changed.")
                return redirect("accounts:profile")
        elif form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form, "pwd_form": pwd_form})
