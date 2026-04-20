# products/templatetags/product_extras.py
from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def get_discounted_price(product, original_price=None):
    """Get discounted price for a product"""
    if hasattr(product, 'discounted_price') and product.discounted_price:
        return product.discounted_price
    
    if hasattr(product, 'discount_percentage') and product.discount_percentage > 0:
        price = original_price or getattr(product, 'price', getattr(product, 'selling_price', 0))
        discount_amount = (price * product.discount_percentage) / 100
        return price - discount_amount
    
    return original_price or getattr(product, 'price', getattr(product, 'selling_price', 0))

@register.filter
def get_savings(product):
    """Get savings amount from discount"""
    if hasattr(product, 'discount_percentage') and product.discount_percentage > 0:
        original_price = getattr(product, 'price', getattr(product, 'selling_price', 0))
        discounted_price = getattr(product, 'discounted_price', original_price)
        return original_price - discounted_price
    return 0

@register.filter
def get_savings_percentage(product):
    """Get savings percentage"""
    if hasattr(product, 'discount_percentage') and product.discount_percentage > 0:
        return product.discount_percentage
    return 0

@register.filter
def format_price(price):
    """Format price with Indian Rupee symbol"""
    return f"₹{price:.2f}"