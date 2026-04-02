from django.shortcuts import render

def home(request):
    return render(request, 'home.html')

def privacy_policy(request):
    return render(request, 'privacy_policy.html')

def terms(request):
    return render(request, 'terms.html')

def about(request):
    return render(request, 'about.html')

def wholeseller_vendor_policy(request):
    return render(request, 'wholeseller_vendor_policy.html')

def reseller_seller_policy(request):
    return render(request, 'reseller_seller_policy.html')

def community_guidelines(request):
    return render(request, 'community_guidelines.html')

def intellectual_property_policy(request):
    return render(request, 'intellectual_property_policy.html')

def return_policy(request):
    return render(request, 'return_policy.html')

def shipping_delivery_policy(request):
    return render(request, 'shipping_delivery_policy.html')

def refund_cancellation_policy(request):
    return render(request, 'refund_cancellation_policy.html')

def cookie_policy(request):
    return render(request, 'cookie_policy.html')

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from .models import Contact
from .forms import ContactForm


# 🔐 Superuser check
def superuser_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


# ✅ PUBLIC CREATE
def contact_create(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Message sent successfully!')
            return redirect('contact_create')
    else:
        form = ContactForm()

    return render(request, 'contact_form.html', {'form': form})


# 🔐 LIST
@superuser_required
def contact_list(request):
    contacts = Contact.objects.all().order_by('-created_at')
    return render(request, 'contact_list.html', {'contacts': contacts})


# 🔐 DETAIL
@superuser_required
def contact_detail(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    return render(request, 'contact_detail.html', {'contact': contact})


# 🔐 DELETE
@superuser_required
def contact_delete(request, pk):
    contact = get_object_or_404(Contact, pk=pk)

    if request.method == 'POST':
        contact.delete()
        messages.success(request, 'Contact deleted successfully!')
        return redirect('contact_list')

    return render(request, 'contact_confirm_delete.html', {'contact': contact})