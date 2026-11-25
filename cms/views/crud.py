from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from accounts.utils import audit

from ..resources import REGISTRY, apply_search


def _resource(slug, user, edit=False):
    res = REGISTRY.get(slug)
    if res is None:
        raise Http404
    if not res.can_view(user) or (edit and not res.can_edit(user)):
        raise PermissionDenied
    return res


@login_required
def resource_list(request, slug):
    res = _resource(slug, request.user)
    qs = res.queryset(request.user)
    term = request.GET.get("q", "").strip()
    qs = apply_search(qs, res, term)
    active_filters = []
    for f in res.filters:
        field = res.model._meta.get_field(f)
        value = request.GET.get(f, "")
        if value != "":
            qs = qs.filter(**{f: value})
        if field.choices:
            options = [(str(k), v) for k, v in field.choices]
        elif field.is_relation:
            options = [(str(o.pk), str(o)) for o in field.related_model.objects.all()[:200]]
        elif field.get_internal_type() == "BooleanField":
            options = [("True", "Yes"), ("False", "No")]
        else:
            options = [(str(v), str(v)) for v in qs.values_list(f, flat=True).distinct()[:50]]
        active_filters.append({"name": f, "label": field.verbose_name.title(), "options": options, "value": value})
    if not qs.ordered:
        qs = qs.order_by("-pk")
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    rows = []
    for obj in page:
        cells = []
        for _, attr in res.columns:
            if callable(attr):
                val = attr(obj)
            else:
                val = getattr(obj, attr, "")
                val = val() if callable(val) else val
            cells.append(val)
        rows.append({"obj": obj, "cells": cells})
    return render(request, "portal/crud/list.html", {
        "res": res, "page": page, "rows": rows, "headers": [c[0] for c in res.columns], "q": term,
        "filters": active_filters, "can_edit": res.can_edit(request.user),
    })


@login_required
def resource_form(request, slug, pk=None):
    res = _resource(slug, request.user, edit=True)
    obj = get_object_or_404(res.queryset(request.user), pk=pk) if pk else None
    Form = res.get_form_class(request.user)
    form = Form(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        created = obj is None
        item = form.save()
        res.before_save(item, request.user, created)
        audit(request, f"{res.slug}.{'create' if created else 'update'}", item)
        messages.success(request, f"{res.title}: '{item}' saved.")
        return redirect("cms:resource_list", slug)
    return render(request, "portal/crud/form.html", {"res": res, "form": form, "obj": obj})


@login_required
def resource_delete(request, slug, pk):
    res = _resource(slug, request.user, edit=True)
    obj = get_object_or_404(res.queryset(request.user), pk=pk)
    if request.method == "POST":
        label = str(obj)
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, f"'{label}' is in use by other records and cannot be deleted.")
            return redirect("cms:resource_list", slug)
        audit(request, f"{res.slug}.delete", label)
        messages.success(request, f"'{label}' deleted.")
        return redirect("cms:resource_list", slug)
    return render(request, "portal/crud/delete.html", {"res": res, "obj": obj})
