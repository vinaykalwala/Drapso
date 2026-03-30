from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from .forms import *
from .models import *
import logging

logger = logging.getLogger(__name__)

def send_otp_email(user, otp, purpose='verification'):
    """Send OTP email"""
    if purpose == 'verification':
        subject = 'Verify Your Email - OTP Code'
        message = f'Hello {user.first_name},\n\nYour OTP code for email verification is: {otp}\n\nThis code is valid for 10 minutes.\n\nThank you!'
    else:
        subject = 'Password Reset OTP'
        message = f'Hello {user.first_name},\n\nYour OTP code for password reset is: {otp}\n\nThis code is valid for 10 minutes.\n\nIf you did not request this, please ignore this email.'
    
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email: {e}")
        return False

# ============ TEMPLATE-BASED SIGNUP VIEWS ============

def wholeseller_signup(request):
    """Wholeseller signup with template"""
    if request.method == 'POST':
        form = WholesellerSignupForm(request.POST, request.FILES)
        if form.is_valid():
            # Create User
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'],
                first_name=form.cleaned_data['first_name'],
                middle_name=form.cleaned_data.get('middle_name', ''),
                last_name=form.cleaned_data['last_name'],
                phone=form.cleaned_data['phone'],
                role=User.Role.WHOLESELLER,
                is_active=False,
                is_verified=False
            )
            
            # Create Wholeseller Profile
            wholeseller_profile = WholesellerProfile.objects.create(
                user=user,
                business_name=form.cleaned_data['business_name'],
                business_type=form.cleaned_data['business_type'],
                business_registration_number=form.cleaned_data['business_registration_number'],
                tax_id=form.cleaned_data.get('tax_id', ''),
                gst_number=form.cleaned_data.get('gst_number', ''),
                business_phone=form.cleaned_data['business_phone'],
                business_email=form.cleaned_data['business_email'],
                website=form.cleaned_data.get('website', ''),
                business_address=form.cleaned_data['business_address'],
                city=form.cleaned_data['city'],
                state=form.cleaned_data['state'],
                country=form.cleaned_data['country'],
                postal_code=form.cleaned_data['postal_code'],
                years_in_business=form.cleaned_data['years_in_business'],
                number_of_employees=form.cleaned_data['number_of_employees'],
                annual_turnover=form.cleaned_data.get('annual_turnover', 0),
                description=form.cleaned_data.get('description', '')
            )
            
            # Generate and send OTP
            otp = user.generate_otp()
            send_otp_email(user, otp, 'verification')
            
            # Store user ID in session for OTP verification
            request.session['pending_user_id'] = user.id
            
            messages.success(request, 'Account created successfully! Please verify your email with the OTP sent.')
            return redirect('accounts:verify_otp')
    else:
        form = WholesellerSignupForm()
    
    return render(request, 'accounts/wholeseller_signup.html', {'form': form, 'title': 'Wholeseller Registration'})

def reseller_signup(request):
    """Reseller signup with template"""
    if request.method == 'POST':
        form = ResellerSignupForm(request.POST, request.FILES)
        if form.is_valid():
            # Create User
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'],
                first_name=form.cleaned_data['first_name'],
                middle_name=form.cleaned_data.get('middle_name', ''),
                last_name=form.cleaned_data['last_name'],
                phone=form.cleaned_data['phone'],
                role=User.Role.RESELLER,
                is_active=False,
                is_verified=False
            )
            
            # Create Reseller Profile
            reseller_profile = ResellerProfile.objects.create(
                user=user,
                company_name=form.cleaned_data.get('company_name', ''),
                reseller_type=form.cleaned_data['reseller_type'],
                tax_id=form.cleaned_data.get('tax_id', ''),
                business_phone=form.cleaned_data['business_phone'],
                business_email=form.cleaned_data['business_email'],
                business_address=form.cleaned_data['business_address'],
                city=form.cleaned_data['city'],
                state=form.cleaned_data['state'],
                country=form.cleaned_data['country'],
                postal_code=form.cleaned_data['postal_code'],
                
            )
            
            # Generate and send OTP
            otp = user.generate_otp()
            send_otp_email(user, otp, 'verification')
            
            # Store user ID in session for OTP verification
            request.session['pending_user_id'] = user.id
            
            messages.success(request, 'Account created successfully! Please verify your email with the OTP sent.')
            return redirect('accounts:verify_otp')
    else:
        form = ResellerSignupForm()
    
    return render(request, 'accounts/reseller_signup.html', {'form': form, 'title': 'Reseller Registration'})

def admin_signup(request):
    """Admin signup with template (restricted - should be protected)"""
    # You might want to restrict this view to superusers only
    if not request.user.is_superuser:
        messages.error(request, 'You do not have permission to create admin accounts.')
        return redirect('accounts:login')
    
    if request.method == 'POST':
        form = AdminSignupForm(request.POST, request.FILES)
        if form.is_valid():
            # Create User
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'],
                first_name=form.cleaned_data['first_name'],
                middle_name=form.cleaned_data.get('middle_name', ''),
                last_name=form.cleaned_data['last_name'],
                phone=form.cleaned_data['phone'],
                role=User.Role.ADMIN,
                is_active=False,
                is_verified=False
            )
            
            # Create Admin Profile
            admin_profile = AdminProfile.objects.create(
                user=user,
                employee_id=form.cleaned_data['employee_id'],
                department=form.cleaned_data['department'],
                designation=form.cleaned_data['designation'],
                office_phone=form.cleaned_data['office_phone'],
                emergency_contact=form.cleaned_data['emergency_contact'],
                office_address=form.cleaned_data['office_address'],
                city=form.cleaned_data['city'],
                state=form.cleaned_data['state'],
                country=form.cleaned_data['country'],
                postal_code=form.cleaned_data['postal_code'],
                permissions_level=int(form.cleaned_data['permissions_level']),
                can_manage_users=form.cleaned_data['can_manage_users'],
                can_manage_products=form.cleaned_data['can_manage_products'],
                can_manage_orders=form.cleaned_data['can_manage_orders'],
                can_view_reports=form.cleaned_data['can_view_reports']
            )
            
            # Generate and send OTP
            otp = user.generate_otp()
            send_otp_email(user, otp, 'verification')
            
            # Store user ID in session for OTP verification
            request.session['pending_user_id'] = user.id
            
            messages.success(request, 'Admin account created successfully! Please verify your email with the OTP sent.')
            return redirect('accounts:verify_otp')
    else:
        form = AdminSignupForm()
    
    return render(request, 'accounts/admin_signup.html', {'form': form, 'title': 'Admin Registration'})

# ============ AUTHENTICATION VIEWS ============

def verify_otp(request):
    """Verify OTP for account activation"""
    if request.method == 'POST':
        form = OTPVerificationForm(request.POST)
        if form.is_valid():
            otp = form.cleaned_data['otp']
            user_id = request.session.get('pending_user_id')
            
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if user.verify_otp(otp):
                        user.is_verified = True
                        user.is_active = True
                        user.clear_otp()
                        user.save()
                        
                        # Log the user in
                        login(request, user)
                        
                        # Clear session
                        del request.session['pending_user_id']
                        
                        messages.success(request, f'Email verified successfully! Welcome {user.first_name}!')
                        return redirect('accounts:dashboard')
                    else:
                        messages.error(request, 'Invalid or expired OTP. Please try again.')
                except User.DoesNotExist:
                    messages.error(request, 'User not found. Please sign up again.')
            else:
                messages.error(request, 'Session expired. Please sign up again.')
    else:
        form = OTPVerificationForm()
    
    return render(request, 'accounts/verify_otp.html', {'form': form})

def resend_otp(request):
    """Resend OTP to user"""
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)
            if not user.is_verified:
                otp = user.generate_otp()
                send_otp_email(user, otp, 'verification')
                messages.success(request, 'New OTP sent to your email.')
            else:
                messages.error(request, 'Email is already verified.')
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
    
    return redirect('accounts:verify_otp')

def login_view(request):
    """Login view supporting username or email"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            login_input = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            
            # Try to find user by email or username
            if '@' in login_input:
                try:
                    user = User.objects.get(email=login_input)
                    username = user.username
                except User.DoesNotExist:
                    username = login_input
            else:
                username = login_input
            
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name}!')
                
                # Redirect based on role
                next_url = request.GET.get('next', 'accounts:dashboard')
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid username/email or password.')
        else:
            messages.error(request, 'Invalid login credentials.')
    else:
        form = LoginForm()
    
    return render(request, 'accounts/login.html', {'form': form})

def forgot_password(request):
    """Forgot password - send OTP"""
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                user = User.objects.get(email=email)
                otp = user.generate_otp()
                if send_otp_email(user, otp, 'reset'):
                    request.session['reset_user_id'] = user.id
                    messages.success(request, 'OTP sent to your email for password reset.')
                    return redirect('accounts:reset_password')
                else:
                    messages.error(request, 'Failed to send OTP. Please try again.')
            except User.DoesNotExist:
                messages.error(request, 'No account found with this email address.')
    else:
        form = ForgotPasswordForm()
    
    return render(request, 'accounts/forgot_password.html', {'form': form})

def reset_password(request):
    """Reset password with OTP"""
    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            otp = form.cleaned_data['otp']
            new_password = form.cleaned_data['new_password']
            user_id = request.session.get('reset_user_id')
            
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if user.verify_otp(otp):
                        user.set_password(new_password)
                        user.clear_otp()
                        user.save()
                        
                        del request.session['reset_user_id']
                        messages.success(request, 'Password reset successful! Please login with your new password.')
                        return redirect('accounts:login')
                    else:
                        messages.error(request, 'Invalid or expired OTP.')
                except User.DoesNotExist:
                    messages.error(request, 'User not found.')
            else:
                messages.error(request, 'Session expired. Please request password reset again.')
    else:
        form = ResetPasswordForm()
    
    return render(request, 'accounts/reset_password.html', {'form': form})

@login_required
def change_password(request):
    """Change password for authenticated user"""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Password changed successfully!')
            return redirect('accounts:dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'accounts/change_password.html', {'form': form})

@login_required
def dashboard(request):
    """Dashboard showing user-specific information"""
    user = request.user
    
    # Get role-specific profile
    profile_data = None
    if user.role == User.Role.WHOLESELLER:
        profile_data = user.wholeseller_profile
    elif user.role == User.Role.RESELLER:
        profile_data = user.reseller_profile
    elif user.role == User.Role.ADMIN:
        profile_data = user.admin_profile
    
    context = {
        'user': user,
        'profile': profile_data,
        'role': user.get_role_display()
    }
    
    return render(request, 'accounts/dashboard.html', context)

@login_required
def logout_view(request):
    """Logout user"""
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('accounts:login')

@login_required
def profile_view(request):
    """View user profile"""
    user = request.user
    profile = None
    
    if hasattr(user, 'profile'):
        profile = user.profile
    
    context = {
        'user': user,
        'profile': profile
    }
    return render(request, 'accounts/profile.html', context)

@login_required
def edit_profile(request):
    """Edit user profile"""
    user = request.user
    
    if request.method == 'POST':
        # Update user fields
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.phone = request.POST.get('phone', user.phone)
        user.save()
        
        # Update or create profile
        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.address = request.POST.get('address', '')
        profile.city = request.POST.get('city', '')
        profile.state = request.POST.get('state', '')
        profile.postal_code = request.POST.get('postal_code', '')
        
        if request.FILES.get('avatar'):
            profile.avatar = request.FILES['avatar']
        
        profile.save()
        
        messages.success(request, 'Profile updated successfully!')
        return redirect('accounts:profile')
    
    return redirect('accounts:profile')
