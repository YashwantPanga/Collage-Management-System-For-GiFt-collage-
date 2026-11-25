from django import template
from django.templatetags.static import static

register = template.Library()


@register.filter
def asset(path, default="brand/hero-campus.jpg"):
    """Resolve an image stored as a static path, absolute URL or media path."""
    path = (path or "").strip() if isinstance(path, str) else (getattr(path, "url", "") if path else "")
    if not path:
        return static(default)
    if path.startswith(("http://", "https://", "/")):
        return path
    return static(path)


@register.filter
def bs(field):
    """Render a bound form field with the right Bootstrap class."""
    widget = field.field.widget
    itype = getattr(widget, "input_type", None)
    if itype in ("checkbox", "radio"):
        css = "form-check-input"
    elif widget.__class__.__name__ in ("Select", "SelectMultiple", "NullBooleanSelect"):
        css = "form-select"
    else:
        css = "form-control"
    if field.errors:
        css += " is-invalid"
    existing = widget.attrs.get("class", "")
    return field.as_widget(attrs={"class": f"{existing} {css}".strip()})


@register.simple_tag(takes_context=True)
def active(context, *names):
    """Return 'active' when the current url name matches one of the names."""
    match = getattr(context.get("request"), "resolver_match", None)
    if match and (match.view_name in names or match.url_name in names):
        return "active"
    return ""
