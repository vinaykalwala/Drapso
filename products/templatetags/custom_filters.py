from django import template

register = template.Library()

@register.filter
def sum_attribute(queryset, attribute):
    """Sum a specific attribute across a queryset"""
    if not queryset:
        return 0
    total = sum(getattr(item, attribute, 0) for item in queryset)
    return total

@register.filter
def subtract(value, arg):
    """Subtract arg from value"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0