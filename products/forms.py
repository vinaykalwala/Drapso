from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from .models import (
    Category, Subcategory, WholesellerProduct, WholesellerProductImage,
    WholesellerProductVariant, WholesellerVariantImage,
    ResellerProduct, ResellerProductImage, ResellerProductVariant,
    ResellerVariantImage, PriceChangeNotification
)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'image', 'is_active', 'order']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class SubcategoryForm(forms.ModelForm):
    class Meta:
        model = Subcategory
        fields = ['category', 'name', 'image', 'is_active', 'order']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
        }


# ============ WHOLESELLER FORMS ============

class WholesellerProductForm(forms.ModelForm):
    class Meta:
        model = WholesellerProduct
        fields = [
            'category', 'subcategory', 'name', 'description', 'specification',
            'brand', 'model_name', 'size', 'color', 'material', 'gender',
            'price', 'stock', 'threshold_limit', 'main_image', 'is_active', 'is_featured'
        ]
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'subcategory': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 5, 'class': 'form-control'}),
            'specification': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'brand': forms.TextInput(attrs={'class': 'form-control'}),
            'model_name': forms.TextInput(attrs={'class': 'form-control'}),
            'size': forms.TextInput(attrs={'class': 'form-control'}),
            'color': forms.TextInput(attrs={'class': 'form-control'}),
            'material': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'threshold_limit': forms.NumberInput(attrs={'class': 'form-control'}),
            'main_image': forms.FileInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_featured': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['category'].queryset = Category.objects.filter(is_active=True)

        # 🔥 HANDLE POST DATA (MOST IMPORTANT FIX)
        if 'category' in self.data:
            try:
                category_id = int(self.data.get('category'))
                self.fields['subcategory'].queryset = Subcategory.objects.filter(
                    category_id=category_id,
                    is_active=True
                )
            except (ValueError, TypeError):
                self.fields['subcategory'].queryset = Subcategory.objects.none()

        # 🔥 HANDLE EDIT CASE
        elif self.instance.pk and self.instance.category:
            self.fields['subcategory'].queryset = Subcategory.objects.filter(
                category=self.instance.category,
                is_active=True
            )

        else:
            self.fields['subcategory'].queryset = Subcategory.objects.none()
class WholesellerVariantForm(forms.ModelForm):
    class Meta:
        model = WholesellerProductVariant
        fields = ['size', 'color', 'price', 'stock', 'threshold_limit', 'main_image', 'order', 'is_active']
        widgets = {
            'size': forms.TextInput(attrs={'class': 'form-control'}),
            'color': forms.TextInput(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'threshold_limit': forms.NumberInput(attrs={'class': 'form-control'}),
            'main_image': forms.FileInput(attrs={'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ============ RESELLER FORMS ============

class ResellerImportProductForm(forms.ModelForm):
    margin_rupees = forms.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'margin_rupees'}),
        help_text="Add your margin in rupees"
    )
    
    class Meta:
        model = ResellerProduct
        fields = ['margin_rupees']
    
    def __init__(self, *args, **kwargs):
        self.wholeseller_product = kwargs.pop('wholeseller_product', None)
        super().__init__(*args, **kwargs)


class ResellerImportProductEditForm(forms.ModelForm):

    margin_rupees = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        label="Margin (₹)"
    )

    class Meta:
        model = ResellerProduct
        fields = []   # 🔥 IMPORTANT: no model fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance:
            self.fields['margin_rupees'].initial = self.instance.margin_rupees
            
class ResellerOwnProductForm(forms.ModelForm):

    class Meta:
        model = ResellerProduct
        fields = [
            'category', 'subcategory', 'name', 'description', 'specification',
            'brand', 'model_name', 'size', 'color', 'material', 'gender',
            'selling_price', 'stock', 'threshold_limit', 'main_image',
            'is_active', 'is_featured', 'is_published'
        ]

        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'subcategory': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 5, 'class': 'form-control'}),
            'specification': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'brand': forms.TextInput(attrs={'class': 'form-control'}),
            'model_name': forms.TextInput(attrs={'class': 'form-control'}),
            'size': forms.TextInput(attrs={'class': 'form-control'}),
            'color': forms.TextInput(attrs={'class': 'form-control'}),
            'material': forms.TextInput(attrs={'class': 'form-control'}),

            # ✅ IMPORTANT
            'gender': forms.Select(attrs={'class': 'form-control'}),

            'selling_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'threshold_limit': forms.NumberInput(attrs={'class': 'form-control'}),
            'main_image': forms.FileInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_featured': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['category'].queryset = Category.objects.filter(is_active=True)

        # ✅ Make gender optional + placeholder
        self.fields['gender'].required = False
        self.fields['gender'].choices = [('', 'Select Gender')] + list(self.fields['gender'].choices)

        # 🔥 Subcategory logic (keep this)
        if self.data.get('category'):
            try:
                category_id = int(self.data.get('category'))
                self.fields['subcategory'].queryset = Subcategory.objects.filter(
                    category_id=category_id,
                    is_active=True
                )
            except:
                self.fields['subcategory'].queryset = Subcategory.objects.none()

        elif self.instance.pk and self.instance.category:
            self.fields['subcategory'].queryset = Subcategory.objects.filter(
                category=self.instance.category,
                is_active=True
            )
        else:
            self.fields['subcategory'].queryset = Subcategory.objects.none()

class ResellerVariantForm(forms.ModelForm):
    class Meta:
        model = ResellerProductVariant
        fields = [
            'size',
            'color',
            'selling_price',   # ✅ instead of margin
            'stock',
            'threshold_limit',
            'main_image',
            'order',
            'is_active'
        ]

        widgets = {
            'size': forms.TextInput(attrs={'class': 'form-control'}),
            'color': forms.TextInput(attrs={'class': 'form-control'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'threshold_limit': forms.NumberInput(attrs={'class': 'form-control'}),
            'main_image': forms.FileInput(attrs={'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

# ============ INLINE FORMSETS FOR MULTIPLE IMAGES ============

WholesellerProductImageFormSet = inlineformset_factory(
    WholesellerProduct,
    WholesellerProductImage,
    fields=('image', 'alt_text', 'order'),
    extra=0,   # IMPORTANT
    can_delete=True
)
# Wholeseller Variant Images Formset
WholesellerVariantImageFormSet = inlineformset_factory(
    WholesellerProductVariant,
    WholesellerVariantImage,
    fields=('image', 'alt_text', 'order'),
    extra=0,
    max_num=10,
    can_delete=True,
    widgets={
        'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        'alt_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Image description'}),
        'order': forms.NumberInput(attrs={'class': 'form-control', 'style': 'width: 80px;'}),
    }
)

ResellerProductImageFormSet = inlineformset_factory(
    ResellerProduct,
    ResellerProductImage,
    fields=('image', 'alt_text', 'order'),
    extra=0,
    can_delete=True,
    widgets={
        'image': forms.FileInput(attrs={'class': 'form-control'}),
        'alt_text': forms.TextInput(attrs={'class': 'form-control'}),
        'order': forms.NumberInput(attrs={'class': 'form-control'}),
    }
)

# Reseller Variant Images Formset
ResellerVariantImageFormSet = inlineformset_factory(
    ResellerProductVariant,
    ResellerVariantImage,
    fields=('image', 'alt_text', 'order'),
    extra=0,
    max_num=10,
    can_delete=True,
    widgets={
        'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        'alt_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Image description'}),
        'order': forms.NumberInput(attrs={'class': 'form-control', 'style': 'width: 80px;'}),
    }
)


# Product Images
ResellerProductImageFormSet = inlineformset_factory(
    ResellerProduct,
    ResellerProductImage,
    fields=('image', 'alt_text', 'order'),
    extra=0,   # 👈 IMPORTANT: start empty
    can_delete=True
)

# Variants
ResellerVariantFormSet = inlineformset_factory(
    ResellerProduct,
    ResellerProductVariant,
    form=ResellerVariantForm,
    extra=0,   # 👈 start empty
    can_delete=True
)