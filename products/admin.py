# products/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Category, Subcategory, WholesellerProduct, WholesellerProductImage,
    WholesellerProductVariant, WholesellerVariantImage,
    ResellerProduct, ResellerProductImage, ResellerProductVariant,
    ResellerVariantImage, PriceChangeNotification
)

admin.site.register(Category)
admin.site.register(Subcategory)
admin.site.register(WholesellerProduct)
admin.site.register(WholesellerProductImage)
admin.site.register(WholesellerProductVariant)
admin.site.register(WholesellerVariantImage)
admin.site.register(ResellerProduct)
admin.site.register(ResellerProductImage)
admin.site.register(ResellerProductVariant)
admin.site.register(ResellerVariantImage)
admin.site.register(PriceChangeNotification)