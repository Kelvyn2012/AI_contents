from django import template

register = template.Library()


@register.filter
def kobo_to_naira(kobo):
    """Convert integer kobo to formatted naira string."""
    try:
        naira = int(kobo) // 100
        return f"₦{naira:,}"
    except (TypeError, ValueError):
        return "—"
