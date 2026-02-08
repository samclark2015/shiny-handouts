from django import template

register = template.Library()


@register.filter
def sum_attr(value_list, attr_name):
    """Sum a specific attribute across a list of dictionaries or objects."""
    if not value_list:
        return 0

    total = 0
    for item in value_list:
        if isinstance(item, dict):
            total += item.get(attr_name, 0)
        else:
            total += getattr(item, attr_name, 0)
    return total
