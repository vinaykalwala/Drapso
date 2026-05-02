# resellers/forms.py

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
import re
from .models import Store, SubscriptionPlan, StoreTheme

# List of restricted brand names
RESTRICTED_STORE_NAMES = {
    'nike', 'adidas', 'puma', 'reebok', 'asics', 'new balance', 'fila',
    'skechers', 'converse', 'vans', 'crocs', 'bata', 'woodland', 'red tape',
    'relaxo', 'paragon', 'liberty', 'sparx', 'campus', 'action', 'khadim’s',
    'metro shoes', 'mochi', 'zara', 'h&m', 'uniqlo', 'levi’s', 'wrangler',
    'lee', 'pepe jeans', 'diesel', 'guess', 'forever 21', 'gap',
    'american eagle', 'hollister', 'abercrombie', 'superdry', 'jack & jones',
    'vero moda', 'only', 'mango', 'marks & spencer', 'next', 'primark',
    'tommy hilfiger', 'calvin klein', 'armani', 'emporio armani', 'giorgio armani',
    'hugo boss', 'ralph lauren', 'lacoste', 'brooks brothers', 'ted baker',
    'michael kors', 'kate spade', 'coach', 'tory burch', 'gucci',
    'louis vuitton', 'chanel', 'dior', 'versace', 'prada', 'burberry',
    'balenciaga', 'givenchy', 'fendi', 'valentino', 'yves saint laurent',
    'bottega veneta', 'hermes', 'cartier', 'rolex', 'omega', 'tag heuer',
    'patek philippe', 'audemars piguet', 'fossil', 'titan', 'fastrack',
    'casio', 'seiko', 'timex', 'swatch', 'tissot', 'hublot', 'montblanc',
    'ray-ban', 'oakley', 'police', 'carrera', 'persol', 'maui jim', 'apple',
    'samsung', 'sony', 'dell', 'hp', 'lenovo', 'asus', 'acer', 'microsoft',
    'google', 'intel', 'amd', 'nvidia', 'qualcomm', 'ibm', 'cisco', 'oracle',
    'sap', 'amazon', 'flipkart', 'meesho', 'ebay', 'shopify', 'myntra',
    'ajio', 'snapdeal', 'tata cliq', 'nykaa', 'bigbasket', 'reliance digital',
    'croma', 'vijay sales', 'walmart', 'target', 'best buy', 'costco',
    'paytm', 'phonepe', 'google pay', 'amazon pay', 'razorpay', 'stripe',
    'paypal', 'visa', 'mastercard', 'rupay', 'swiggy', 'zomato', 'ola',
    'uber', 'rapido', 'dunzo', 'blinkit', 'zepto', 'netflix', 'amazon prime',
    'disney+ hotstar', 'sony liv', 'zee5', 'jiocinema', 'instagram',
    'facebook', 'whatsapp', 'twitter', 'youtube', 'linkedin', 'snapchat',
    'telegram', 'pinterest', 'reddit', 'tumblr', 'threads', 'discord', 'tesla',
    'bmw', 'audi', 'mercedes', 'toyota', 'honda', 'hyundai', 'kia', 'ford',
    'volkswagen', 'skoda', 'nissan', 'renault', 'mahindra', 'tata motors',
    'jeep', 'jaguar', 'land rover', 'volvo', 'porsche', 'ferrari',
    'lamborghini', 'bentley', 'rolls royce', 'bugatti', 'maserati',
    'alfa romeo', 'harley davidson', 'royal enfield', 'bajaj', 'hero', 'tvs',
    'yamaha', 'suzuki', 'kawasaki', 'ktm', 'ducati', 'triumph', 'aprilia',
    'vespa', 'piaggio', 'shell', 'castrol', 'indian oil', 'bharat petroleum',
    'hindustan petroleum', 'jio', 'airtel', 'vodafone', 'icici bank',
    'hdfc bank', 'sbi', 'axis bank', 'kotak mahindra bank', 'yes bank',
    'indusind bank', 'bank of baroda', 'canara bank', 'punjab national bank',
    'idfc first bank', 'federal bank', 'rbl bank', 'hsbc', 'citi bank',
    'deutsche bank', 'standard chartered', 'barclays', 'wells fargo',
    'jpmorgan chase', 'goldman sachs', 'morgan stanley', 'starbucks',
    "mcdonald's", 'kfc', 'burger king', "domino's", 'pizza hut', 'subway',
    'taco bell', 'dunkin donuts', 'baskin robbins', 'barista', 'cafe coffee day',
    'costa coffee', 'tim hortons', 'nestle', 'amul', 'britannia', 'cadbury',
    'hershey’s', 'ferrero rocher', 'kitkat', 'mars', 'snickers', 'bounty',
    'twix', 'pepsi', 'coca cola', 'sprite', 'fanta', 'mountain dew', 'red bull',
    'tropicana', 'real', 'minute maid', 'bisleri', 'aquafina', 'kinley',
    'evian', 'perrier', 'patanjali', 'himalaya', 'dabur', 'colgate',
    'pepsodent', 'closeup', 'oral-b', 'gillette', 'dettol', 'lifebuoy',
    'lux', 'dove', 'pears', 'santoor', 'surf excel', 'ariel', 'tide', 'rin',
    'wheel', 'vim', 'harpic', 'lizol', 'godrej', 'itc', 'hindustan unilever',
    'procter & gamble', 'johnson & johnson', 'reckitt', "l'oréal", 'maybelline',
    'lakmé', 'nivea', 'garnier', 'ponds', 'olay', 'revlon', 'mac',
    'estee lauder', 'clinique', 'shiseido', 'sephora', 'nykaa cosmetics',
    'mamaearth', 'wow skin science', 'biotique', 'forest essentials', 'vlcc',
    'lotus herbals', 'fabindia', 'decathlon', 'ikea', 'home centre',
    'pepperfry', 'urban ladder', 'wayfair', 'ashley furniture', 'asian paints',
    'nerolac', 'berger paints', 'dulux', 'havells', 'crompton',
    'bajaj electricals', 'philips', 'panasonic', 'lg', 'whirlpool',
    'samsung appliances', 'godrej appliances', 'voltas', 'blue star', 'hitachi',
    'daikin', 'carrier', 'toshiba', 'sharp', 'canon', 'nikon', 'gopro', 'dji',
    'logitech', 'kingston', 'sandisk', 'wd', 'seagate', 'jbl', 'bose',
    'sony audio', 'sennheiser', 'boat', 'noise', 'fire-boltt', 'oneplus',
    'xiaomi', 'redmi', 'poco', 'oppo', 'vivo', 'realme', 'honor', 'huawei',
    'nothing', 'lava', 'micromax', 'infinix', 'tecno', 'blackberry', 'nokia',
    'motorola', 'htc', 'alcatel', 'siemens', 'ericsson', 'spacex',
    'blue origin', 'openai', 'meta', 'alphabet', 'tencent', 'alibaba',
    'baidu', 'bytedance', 'tiktok', 'wechat', 'payoneer', 'wise', 'skrill',
    'western union', 'moneygram', 'adobe', 'zoho', 'freshworks', 'tally',
    'quickbooks', 'xero', 'salesforce', 'hubspot', 'slack', 'zoom', 'dropbox',
    'notion', 'atlassian', 'jira', 'trello', 'canva', 'figma', 'shutterstock',
    'getty images', 'unsplash', 'pexels', 'github', 'gitlab', 'bitbucket',
    'stack overflow', 'medium', 'quora', 'coursera', 'udemy', "byju's",
    'unacademy', 'vedantu', 'physicswallah', 'khan academy', 'edx', 'udacity',
    'skillshare', 'airbnb', 'oyo', 'makemytrip', 'goibibo', 'yatra', 'cleartrip',
    'booking.com', 'expedia', 'agoda', 'trivago', 'thomas cook', 'cox & kings',
    'irctc', 'orange', 't-mobile', 'verizon', 'at&t', 'comcast', 'sky',
    'bt group', 'telstra', 'rogers', 'bell canada', 'telus', 'ntt', 'softbank',
    'rakuten', 'sk telecom', 'kt corporation', 'china mobile', 'china telecom',
    'china unicom', 'booking', 'expedia'
}


def check_restricted_brand_name(store_name):
    """
    Check if store name contains any restricted brand name.
    Returns (is_restricted, matched_brand)
    """
    if not store_name:
        return False, None
    
    normalized_name = store_name.lower().strip()
    
    # Remove common separators and extra characters for better matching
    cleaned_name = re.sub(r'[-_\s]+', '', normalized_name)
    
    for restricted_brand in RESTRICTED_STORE_NAMES:
        # Remove spaces and special chars from restricted brand for comparison
        cleaned_brand = re.sub(r'[-_\s\+\&]+', '', restricted_brand)
        
        # Check if the restricted brand appears as a substring
        if cleaned_brand in cleaned_name or restricted_brand in normalized_name:
            return True, restricted_brand
    
    return False, None


class StoreCreationForm(forms.ModelForm):
    """Step 1: Create store with basic details"""
    
    class Meta:
        model = Store
        fields = [
            'store_name', 'store_description', 'contact_email', 
            'contact_phone', 'store_address', 'store_logo', 'store_banner'
        ]
        widgets = {
            'store_description': forms.Textarea(attrs={
                'rows': 3, 
                'placeholder': 'Describe what your store sells...',
                'class': 'form-control'
            }),
            'store_address': forms.Textarea(attrs={
                'rows': 2, 
                'placeholder': 'Your business address',
                'class': 'form-control'
            }),
            'contact_email': forms.EmailInput(attrs={
                'placeholder': 'store@example.com',
                'class': 'form-control'
            }),
            'contact_phone': forms.TextInput(attrs={
                'placeholder': '+1234567890',
                'class': 'form-control'
            }),
            'store_name': forms.TextInput(attrs={
                'placeholder': 'myawesomestore',
                'class': 'form-control',
            }),
            'store_logo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'store_banner': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }
    
    def clean_store_name(self):
        store_name = self.cleaned_data.get('store_name')
        
        if not store_name:
            raise ValidationError('Store name is required.')
        
        # Check for existing store
        if Store.objects.filter(store_name__iexact=store_name).exists():
            raise ValidationError('This store name is already taken.')
        
        # Validate format (only letters)
        if not re.match(r'^[a-zA-Z]+$', store_name):
            raise ValidationError('Store name can only contain letters (no numbers, spaces, or special characters).')
        
        if len(store_name) < 3:
            raise ValidationError('Store name must be at least 3 characters long.')
        
        if len(store_name) > 50:
            raise ValidationError('Store name must be at most 50 characters long.')
        
        # Check against restricted brand names (substring match)
        is_restricted, matched_brand = check_restricted_brand_name(store_name)
        if is_restricted:
            raise ValidationError(
                f'Your store name contains the restricted brand name "{matched_brand}". '
                f'Please choose a different store name that does not include brand names.'
            )
        
        return store_name.lower()


class StoreEditForm(forms.ModelForm):
    """Edit store details ONLY (no plan/theme logic)"""

    class Meta:
        model = Store
        fields = [
            'store_name', 'store_description', 'contact_email',
            'contact_phone', 'store_address', 'store_logo', 'store_banner'
        ]

        widgets = {
            'store_description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control'
            }),
            'store_address': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control'
            }),
            'contact_email': forms.EmailInput(attrs={
                'class': 'form-control'
            }),
            'contact_phone': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'store_name': forms.TextInput(attrs={
                'class': 'form-control',
            }),
            'store_logo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'store_banner': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }

    def clean_store_name(self):
        store_name = self.cleaned_data.get('store_name')

        if not store_name:
            return store_name

        # Validate format (letters, numbers, hyphens)
        if not re.match(r'^[a-zA-Z0-9-]+$', store_name):
            raise ValidationError(
                'Store name can only contain letters, numbers, and hyphens.'
            )

        if len(store_name) < 3:
            raise ValidationError('Store name must be at least 3 characters long.')
        
        if len(store_name) > 50:
            raise ValidationError('Store name must be at most 50 characters long.')

        # Check against restricted brand names (substring match)
        is_restricted, matched_brand = check_restricted_brand_name(store_name)
        if is_restricted:
            raise ValidationError(
                f'Your store name contains the restricted brand name "{matched_brand}". '
                f'Please choose a different store name that does not include brand names.'
            )

        # Exclude current instance
        qs = Store.objects.filter(store_name__iexact=store_name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError('This store name is already taken.')

        return store_name.lower()

    def clean_contact_email(self):
        email = self.cleaned_data.get('contact_email')
        if email:
            try:
                validate_email(email)
            except ValidationError:
                raise ValidationError('Enter a valid email address.')
        return email


class PlanSelectionForm(forms.Form):
    """Step 2: Select subscription plan"""
    
    plan_id = forms.ModelChoiceField(
        queryset=SubscriptionPlan.objects.filter(is_active=True),
        widget=forms.RadioSelect,
        empty_label=None,
        label="Select Subscription Plan"
    )


class ThemeSelectionForm(forms.Form):
    """Step 3: Select theme (only 2 options)"""
    
    theme_id = forms.ModelChoiceField(
        queryset=StoreTheme.objects.filter(is_active=True),
        widget=forms.RadioSelect,
        empty_label=None,
        label="Select Store Theme"
    )