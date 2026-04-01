# wholesellers/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.db import models

# Import User model - adjust based on your project structure
# If User model is in accounts app:
from accounts.models import User

# If User model is in the same app (wholesellers), use:
# from django.contrib.auth import get_user_model
# User = get_user_model()

from .models import WholesellerInventory, WholesellerKYC
from .forms import WholesellerInventoryForm, WholesellerKYCForm


def is_wholeseller(user):
    """Check if user is a wholeseller"""
    return user.is_authenticated and user.role == User.Role.WHOLESELLER


@login_required
@user_passes_test(is_wholeseller)
def create_inventory(request):
    """Step 1: Create inventory/business info"""
    
    # Check if inventory already exists
    if hasattr(request.user, 'inventory'):
        messages.info(request, 'You already have an inventory setup. Proceed to KYC submission.')
        return redirect('wholesellers:submit_kyc')
    
    if request.method == 'POST':
        form = WholesellerInventoryForm(request.POST)
        if form.is_valid():
            inventory = form.save(commit=False)
            inventory.wholeseller = request.user
            inventory.save()
            
            messages.success(request, '✓ Inventory created successfully! Now please submit your KYC documents.')
            return redirect('wholesellers:submit_kyc')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = WholesellerInventoryForm()
    
    return render(request, 'wholeseller/create_inventory.html', {'form': form})


@login_required
@user_passes_test(is_wholeseller)
def submit_kyc(request):
    """Step 2: Submit KYC documents"""
    
    # Check if inventory exists
    try:
        inventory = request.user.inventory
    except WholesellerInventory.DoesNotExist:
        messages.error(request, 'Please create your inventory first.')
        return redirect('wholesellers:create_inventory')
    
    # Check if already verified
    if inventory.is_verified:
        messages.success(request, '✅ Your account is already verified! You can now add products.')
        return redirect('wholesellers:wholeseller_dashboard')
    
    # Get or create KYC record
    kyc, created = WholesellerKYC.objects.get_or_create(wholeseller=request.user)
    
    # If KYC already submitted and pending, show info message
    if not created and kyc.status == 'pending':
        messages.info(request, 'Your KYC documents are currently under review by admin. You will be notified once verified.')
        return redirect('wholesellers:wholeseller_dashboard')
    
    # If KYC rejected, show warning
    if not created and kyc.status == 'rejected':
        messages.warning(request, f'Your previous KYC submission was rejected. Reason: {kyc.rejection_reason}. Please resubmit with correct documents.')
    
    if request.method == 'POST':
        form = WholesellerKYCForm(request.POST, request.FILES, instance=kyc)
        if form.is_valid():
            kyc = form.save(commit=False)
            kyc.wholeseller = request.user
            kyc.status = 'pending'
            kyc.save()
            
            # Mark inventory as KYC submitted
            inventory.is_kyc_submitted = True
            inventory.save()
            
            messages.success(request, '📄 KYC documents submitted successfully! Admin will review and verify your account within 24-48 hours.')
            return redirect('wholesellers:wholeseller_dashboard')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = WholesellerKYCForm(instance=kyc)
    
    context = {
        'form': form,
        'inventory': inventory,
        'kyc': kyc,
        'documents_uploaded': kyc.get_documents_count(),
    }
    return render(request, 'wholeseller/submit_kyc.html', context)


@login_required
@user_passes_test(is_wholeseller)
def wholeseller_dashboard(request):
    """Wholeseller dashboard showing verification status"""
    
    try:
        inventory = request.user.inventory
    except WholesellerInventory.DoesNotExist:
        return redirect('wholesellers:create_inventory')
    
    try:
        kyc = request.user.kyc
    except WholesellerKYC.DoesNotExist:
        kyc = None
    
    # Calculate verification progress
    progress = 0
    if inventory.is_verified:
        progress = 100
    elif kyc and kyc.status == 'pending':
        progress = 75
    elif inventory.is_kyc_submitted:
        progress = 50
    elif hasattr(request.user, 'inventory'):
        progress = 25
    
    context = {
        'inventory': inventory,
        'kyc': kyc,
        'is_verified': inventory.is_verified,
        'kyc_status': kyc.status if kyc else 'not_submitted',
        'progress': progress,
        'business_types': dict(WholesellerInventory.BUSINESS_TYPES),
    }
    return render(request, 'wholeseller/kycdashboard.html', context)


@login_required
@user_passes_test(is_wholeseller)
def edit_inventory(request):
    """Edit inventory details"""
    
    try:
        inventory = request.user.inventory
    except WholesellerInventory.DoesNotExist:
        messages.error(request, 'Inventory not found.')
        return redirect('wholesellers:create_inventory')
    
    if inventory.is_verified:
        messages.warning(request, 'Your inventory is verified. Contact admin for changes.')
        return redirect('wholesellers:wholeseller_dashboard')
    
    if request.method == 'POST':
        form = WholesellerInventoryForm(request.POST, instance=inventory)
        if form.is_valid():
            form.save()
            messages.success(request, 'Inventory details updated successfully!')
            return redirect('wholesellers:wholeseller_dashboard')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = WholesellerInventoryForm(instance=inventory)
    
    return render(request, 'wholeseller/edit_inventory.html', {'form': form, 'inventory': inventory})


# ============ ADMIN VIEWS ============

def is_admin(user):
    """Check if user is admin/staff"""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@login_required
@user_passes_test(is_admin)
def admin_pending_kyc(request):
    """List all pending KYC submissions"""
    
    pending_kyc = WholesellerKYC.objects.filter(status='pending').select_related('wholeseller', 'wholeseller__inventory')
    
    context = {
        'pending_kyc': pending_kyc,
        'total_pending': pending_kyc.count(),
    }
    return render(request, 'wholeseller/pending_kyc.html', context)


@login_required
@user_passes_test(is_admin)
def admin_review_kyc(request, kyc_id):
    """Review individual KYC submission"""
    
    kyc = get_object_or_404(WholesellerKYC, id=kyc_id)
    inventory = kyc.wholeseller.inventory
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            # Approve KYC
            kyc.status = 'approved'
            kyc.verified_by = request.user
            kyc.verified_at = timezone.now()
            kyc.rejection_reason = ''
            kyc.save()
            
            # Mark inventory as verified
            inventory.is_verified = True
            inventory.save()
            
            # Send approval email
            try:
                send_mail(
                    subject='✅ Wholeseller Account Verified - Drapso',
                    message=f"""
Dear {kyc.wholeseller.first_name},

Congratulations! Your wholeseller account has been verified successfully.

Business Details:
• Business Name: {inventory.business_name}
• Business Type: {inventory.get_business_type_display()}
• Warehouse: {inventory.warehouse_name}

You can now:
✓ Add products to your inventory
✓ Manage your stock
✓ Start selling to resellers

Login to your dashboard to get started.

Regards,
Drapso Team
                    """,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[kyc.wholeseller.email],
                    fail_silently=False,
                )
            except Exception as e:
                messages.warning(request, f'KYC approved but email notification failed: {e}')
            
            messages.success(request, f'✅ KYC for {kyc.wholeseller.username} approved successfully')
            
        elif action == 'reject':
            rejection_reason = request.POST.get('rejection_reason')
            
            if not rejection_reason:
                messages.error(request, 'Please provide a rejection reason')
                return redirect('wholesellers:admin_review_kyc', kyc_id=kyc.id)
            
            kyc.status = 'rejected'
            kyc.rejection_reason = rejection_reason
            kyc.save()
            
            # Send rejection email
            try:
                send_mail(
                    subject='⚠️ Wholeseller Account Verification - Update Required',
                    message=f"""
Dear {kyc.wholeseller.first_name},

Your wholeseller verification requires attention.

Reason for rejection:
{rejection_reason}

Please login to your account, update the required documents, and resubmit for verification.

If you have any questions, please contact our support team.

Regards,
Drapso Team
                    """,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[kyc.wholeseller.email],
                    fail_silently=False,
                )
            except Exception as e:
                messages.warning(request, f'KYC rejected but email notification failed: {e}')
            
            messages.success(request, f'❌ KYC for {kyc.wholeseller.username} rejected')
        
        return redirect('wholesellers:admin_pending_kyc')
    
    context = {
        'kyc': kyc,
        'inventory': inventory,
        'documents': {
            'GST Certificate': {
                'file': kyc.gst_certificate,
                'number': kyc.gst_number,
                'icon': '📄'
            },
            'PAN Card': {
                'file': kyc.pan_card,
                'number': kyc.pan_number,
                'icon': '🪪'
            },
            'Address Proof': {
                'file': kyc.address_proof,
                'number': '',
                'icon': '🏠'
            },
            'Business Registration': {
                'file': kyc.business_registration,
                'number': '',
                'icon': '🏢'
            },
            'Warehouse Photo': {
                'file': kyc.warehouse_photo,
                'number': '',
                'icon': '📸'
            },
        }
    }
    return render(request, 'wholeseller/review_kyc.html', context)


@login_required
@user_passes_test(is_admin)
def admin_verified_wholesellers(request):
    """List all verified wholesellers"""
    
    verified_inventories = WholesellerInventory.objects.filter(is_verified=True).select_related('wholeseller')
    
    context = {
        'verified_inventories': verified_inventories,
        'total_verified': verified_inventories.count(),
    }
    return render(request, 'wholeseller/verified_wholesellers.html', context)