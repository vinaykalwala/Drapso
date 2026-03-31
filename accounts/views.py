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
import json

logger = logging.getLogger(__name__)
from django.core.cache import cache
import time

def is_rate_limited(key, limit=3, window=300):
    now = int(time.time())
    data = cache.get(key, [])

    data = [t for t in data if now - t < window]

    if len(data) >= limit:
        return True

    data.append(now)
    cache.set(key, data, timeout=window)
    return False


def send_otp_email(email, first_name, purpose='verification', request=None):
    """Rate-limited OTP generation + email - without user object"""
    
    user_key = f"otp_email_{purpose}_{email}"
    ip = request.META.get('REMOTE_ADDR') if request else None
    ip_key = f"otp_ip_{purpose}_{ip}" if ip else None

    # 🚫 Rate limit check FIRST
    if is_rate_limited(user_key, limit=3, window=300):
        if request:
            messages.error(request, "Too many OTP requests. Try again after 5 minutes.")
        return False

    if ip_key and is_rate_limited(ip_key, limit=10, window=300):
        if request:
            messages.error(request, "Too many requests from your network.")
        return False

    # Generate OTP and store in cache (not in database)
    import random
    otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    # Store OTP in cache with 10 minute expiry
    cache.set(f"otp_{purpose}_{email}", {
        'otp': otp,
        'created_at': time.time(),
        'attempts': 0
    }, timeout=600)  # 10 minutes

    # Email content
    if purpose == 'verification':
        subject = 'Verify Your Email - OTP Code'
        message = f'Hello {first_name},\n\nYour OTP is: {otp}\n\nValid for 10 minutes.\n\nPlease verify your email to complete registration.'
    else:
        subject = 'Password Reset OTP'
        message = f'Hello {first_name},\n\nYour OTP is: {otp}\n\nValid for 10 minutes.'

    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email])
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email: {e}")
        return False

# ============ TEMPLATE-BASED SIGNUP VIEWS ============
from django.contrib.messages import get_messages

def clear_messages(request):
    storage = get_messages(request)
    for _ in storage:
        pass

def wholeseller_signup(request):
    if request.method == 'POST':
        clear_messages(request)
        form = WholesellerSignupForm(request.POST, request.FILES)

        if form.is_valid():
            cleaned_data = form.cleaned_data
            
            # Check if user with this email already exists and is verified
            if User.objects.filter(email=cleaned_data['email'], is_verified=True).exists():
                messages.error(request, 'An account with this email already exists. Please login.')
                return redirect('accounts:login')
            
            # Check if there's a pending registration with this email
            pending_email_key = f"pending_registration_{cleaned_data['email']}"
            if cache.get(pending_email_key):
                messages.error(request, 'A pending registration already exists. Please verify your OTP or request a new one.')
                return redirect('accounts:verify_otp')
            
            # Store registration data in session
            request.session['pending_registration'] = {
                'type': 'wholeseller',
                'data': {
                    'username': cleaned_data['username'],
                    'email': cleaned_data['email'],
                    'password': cleaned_data['password'],
                    'first_name': cleaned_data['first_name'],
                    'middle_name': cleaned_data.get('middle_name', ''),
                    'last_name': cleaned_data['last_name'],
                    'phone': cleaned_data['phone'],
                    'role': User.Role.WHOLESELLER,
                    'profile_data': {
                        'business_name': cleaned_data['business_name'],
                        'business_type': cleaned_data['business_type'],
                        'business_registration_number': cleaned_data['business_registration_number'],
                        'business_phone': cleaned_data['business_phone'],
                        'business_email': cleaned_data['business_email'],
                        'business_address': cleaned_data['business_address'],
                        'city': cleaned_data['city'],
                        'state': cleaned_data['state'],
                        'country': cleaned_data['country'],
                        'postal_code': cleaned_data['postal_code'],
                        'years_in_business': cleaned_data['years_in_business'],
                        'number_of_employees': cleaned_data['number_of_employees'],
                    }
                }
            }
            
            # Mark email as having pending registration
            cache.set(pending_email_key, True, timeout=600)  # 10 minutes

            # Send OTP
            if not send_otp_email(cleaned_data['email'], cleaned_data['first_name'], 'verification', request):
                request.session.pop('pending_registration', None)
                cache.delete(pending_email_key)
                return redirect(request.path)

            messages.success(request, 'Please verify your email with the OTP sent to your inbox.')
            return redirect('accounts:verify_otp')

    else:
        form = WholesellerSignupForm()

    return render(request, 'accounts/wholeseller_signup.html', {'form': form})

def reseller_signup(request):
    if request.method == 'POST':
        clear_messages(request)
        form = ResellerSignupForm(request.POST, request.FILES)

        if form.is_valid():
            cleaned_data = form.cleaned_data
            
            # Check if user already exists and is verified
            if User.objects.filter(email=cleaned_data['email'], is_verified=True).exists():
                messages.error(request, 'An account with this email already exists. Please login.')
                return redirect('accounts:login')
            
            # Check for pending registration
            pending_email_key = f"pending_registration_{cleaned_data['email']}"
            if cache.get(pending_email_key):
                messages.error(request, 'A pending registration already exists. Please verify your OTP or request a new one.')
                return redirect('accounts:verify_otp')
            
            # Store registration data in session
            request.session['pending_registration'] = {
                'type': 'reseller',
                'data': {
                    'username': cleaned_data['username'],
                    'email': cleaned_data['email'],
                    'password': cleaned_data['password'],
                    'first_name': cleaned_data['first_name'],
                    'middle_name': cleaned_data.get('middle_name', ''),
                    'last_name': cleaned_data['last_name'],
                    'phone': cleaned_data['phone'],
                    'role': User.Role.RESELLER,
                    'profile_data': {
                        'reseller_type': cleaned_data['reseller_type'],
                        'business_phone': cleaned_data['business_phone'],
                        'business_email': cleaned_data['business_email'],
                        'business_address': cleaned_data['business_address'],
                        'city': cleaned_data['city'],
                        'state': cleaned_data['state'],
                        'country': cleaned_data['country'],
                        'postal_code': cleaned_data['postal_code'],
                    }
                }
            }
            
            cache.set(pending_email_key, True, timeout=600)

            if not send_otp_email(cleaned_data['email'], cleaned_data['first_name'], 'verification', request):
                request.session.pop('pending_registration', None)
                cache.delete(pending_email_key)
                return redirect(request.path)

            messages.success(request, 'Please verify your email with the OTP sent to your inbox.')
            return redirect('accounts:verify_otp')

    else:
        form = ResellerSignupForm()

    return render(request, 'accounts/reseller_signup.html', {'form': form})

def admin_signup(request):
    """Admin signup with OTP verification - only accessible to existing superusers"""
    if not request.user.is_superuser:
        clear_messages(request)
        messages.error(request, 'No permission. Only superusers can create admin accounts.')
        return redirect('accounts:login')

    if request.method == 'POST':
        clear_messages(request)
        form = AdminSignupForm(request.POST, request.FILES)

        if form.is_valid():
            cleaned_data = form.cleaned_data
            
            # Check if user already exists
            if User.objects.filter(email=cleaned_data['email']).exists():
                messages.error(request, 'An account with this email already exists.')
                return render(request, 'accounts/admin_signup.html', {'form': form})
            
            if User.objects.filter(username=cleaned_data['username']).exists():
                messages.error(request, 'A user with this username already exists.')
                return render(request, 'accounts/admin_signup.html', {'form': form})
            
            # Check for pending registration
            pending_email_key = f"pending_registration_{cleaned_data['email']}"
            if cache.get(pending_email_key):
                messages.error(request, 'A pending registration already exists. Please verify your OTP or request a new one.')
                return redirect('accounts:verify_otp')
            
            # Store registration data in session
            request.session['pending_registration'] = {
                'type': 'admin',
                'is_superuser': True,  # Flag to create superuser
                'auto_login': False,    # 🔥 Don't auto-login after verification
                'created_by': request.user.id,  # Track who created this admin
                'data': {
                    'username': cleaned_data['username'],
                    'email': cleaned_data['email'],
                    'password': cleaned_data['password'],
                    'first_name': cleaned_data['first_name'],
                    'middle_name': cleaned_data.get('middle_name', ''),
                    'last_name': cleaned_data['last_name'],
                    'phone': cleaned_data['phone'],
                    'role': User.Role.ADMIN,
                    'profile_data': {
                        'employee_id': cleaned_data['employee_id'],
                        'department': cleaned_data['department'],
                        'designation': cleaned_data['designation'],
                        'office_phone': cleaned_data['office_phone'],
                        'emergency_contact': cleaned_data['emergency_contact'],
                        'office_address': cleaned_data['office_address'],
                        'city': cleaned_data['city'],
                        'state': cleaned_data['state'],
                        'country': cleaned_data['country'],
                        'postal_code': cleaned_data['postal_code'],
                    }
                }
            }
            
            cache.set(pending_email_key, True, timeout=600)

            # Send OTP
            if not send_otp_email(cleaned_data['email'], cleaned_data['first_name'], 'verification', request):
                request.session.pop('pending_registration', None)
                cache.delete(pending_email_key)
                return redirect(request.path)

            messages.success(request, f'OTP sent to {cleaned_data["email"]}. Please verify to complete admin account creation.')
            return redirect('accounts:verify_otp')  # Use same verify_otp view

    else:
        form = AdminSignupForm()

    return render(request, 'accounts/admin_signup.html', {'form': form})
# ============ AUTHENTICATION VIEWS ============

def verify_otp(request):
    if request.method == 'POST':
        clear_messages(request)
        form = OTPVerificationForm(request.POST)

        if form.is_valid():
            otp = form.cleaned_data['otp']
            pending_registration = request.session.get('pending_registration')
            
            if not pending_registration:
                messages.error(request, 'No pending registration found. Please sign up again.')
                return redirect('accounts:login')
            
            email = pending_registration['data']['email']
            
            # Verify OTP from cache
            otp_data = cache.get(f"otp_verification_{email}")
            
            if not otp_data:
                messages.error(request, 'OTP expired. Please request a new one.')
                return redirect('accounts:resend_otp')
            
            if otp_data['otp'] == otp:
                # ✅ Create user only after successful OTP verification
                data = pending_registration['data']
                
                try:
                    # Check if this is an admin (superuser) registration
                    is_admin_registration = pending_registration.get('is_superuser', False)
                    registration_type = pending_registration.get('type')
                    auto_login = pending_registration.get('auto_login', True)  # Default to True for regular users
                    
                    if is_admin_registration and registration_type == 'admin':
                        # Create superuser for admin registration
                        user = User.objects.create_superuser(
                            username=data['username'],
                            email=data['email'],
                            password=data['password'],
                            first_name=data['first_name'],
                            middle_name=data.get('middle_name', ''),
                            last_name=data['last_name'],
                            phone=data['phone'],
                            role=data['role'],
                            is_active=True,
                            is_verified=True,
                            is_staff=True,
                            is_superuser=True
                        )
                    else:
                        # Create regular user for wholeseller/reseller
                        user = User.objects.create_user(
                            username=data['username'],
                            email=data['email'],
                            password=data['password'],
                            first_name=data['first_name'],
                            middle_name=data.get('middle_name', ''),
                            last_name=data['last_name'],
                            phone=data['phone'],
                            role=data['role'],
                            is_active=True,
                            is_verified=True
                        )
                    
                    # Create the corresponding profile
                    if registration_type == 'wholeseller':
                        WholesellerProfile.objects.create(
                            user=user,
                            **data['profile_data']
                        )
                    elif registration_type == 'reseller':
                        ResellerProfile.objects.create(
                            user=user,
                            **data['profile_data']
                        )
                    elif registration_type == 'admin':
                        AdminProfile.objects.create(
                            user=user,
                            **data['profile_data']
                        )
                    
                    # Clear pending registration data
                    request.session.pop('pending_registration', None)
                    cache.delete(f"pending_registration_{email}")
                    cache.delete(f"otp_verification_{email}")
                    
                    # Only login if auto_login is True (for regular users)
                    if auto_login:
                        login(request, user)
                        messages.success(request, 'Email verified successfully! Welcome to the platform.')
                    else:
                        # For admin creation by superuser, don't login
                        messages.success(request, f'Admin account for {user.get_full_name()} ({user.email}) has been created successfully!')
                        
                        # Optional: Send welcome email to new admin
                        try:
                            send_mail(
                                'Welcome to Admin Dashboard',
                                f'Hello {user.first_name},\n\nYour admin account has been created. '
                                f'You can now login using your credentials.\n\n'
                                f'Username: {user.username}\n'
                                f'Email: {user.email}\n\n'
                                f'Login URL: {request.build_absolute_uri(reverse("accounts:login"))}',
                                settings.DEFAULT_FROM_EMAIL,
                                [user.email],
                                fail_silently=True,
                            )
                        except Exception as e:
                            logger.error(f"Failed to send welcome email: {e}")
                    
                    return redirect('accounts:dashboard' if auto_login else 'accounts:admin_list')
                    
                except Exception as e:
                    logger.error(f"Error creating user after OTP verification: {e}")
                    messages.error(request, 'Error creating account. Please try again.')
                    return redirect('accounts:login')
                    
            else:
                # Increment attempt count
                otp_data['attempts'] = otp_data.get('attempts', 0) + 1
                cache.set(f"otp_verification_{email}", otp_data, timeout=600)
                
                if otp_data['attempts'] >= 5:
                    cache.delete(f"otp_verification_{email}")
                    messages.error(request, 'Too many invalid attempts. Please request a new OTP.')
                    return redirect('accounts:resend_otp')
                
                messages.error(request, 'Invalid OTP. Please try again.')

    else:
        form = OTPVerificationForm()

    return render(request, 'accounts/verify_otp.html', {'form': form})

def resend_otp(request):
    """Resend OTP to user"""
    if request.method == 'POST':
        clear_messages(request)
        pending_registration = request.session.get('pending_registration')
        
        if not pending_registration:
            messages.error(request, 'No pending registration found.')
            return redirect('accounts:login')
        
        email = pending_registration['data']['email']
        first_name = pending_registration['data']['first_name']
        
        # Delete old OTP
        cache.delete(f"otp_verification_{email}")
        
        # Send new OTP
        if send_otp_email(email, first_name, 'verification', request):
            messages.success(request, 'New OTP sent to your email.')
        else:
            messages.error(request, 'Failed to send OTP. Please try again later.')
    
    return redirect('accounts:verify_otp')

def login_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        clear_messages(request)
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user:
            if not user.is_verified:
                messages.error(request, 'Verify your email first.')
                return redirect('accounts:verify_otp')

            login(request, user)
            return redirect('accounts:dashboard')

        messages.error(request, 'Invalid credentials')

    return render(request, 'accounts/login.html')
    
def forgot_password(request):
    if request.method == 'POST':
        clear_messages(request)
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                user = User.objects.get(email=email)

                # For password reset, we need to send OTP differently since user exists
                # You'll need to implement send_otp_email for existing users
                # For now, using the existing user-based OTP
                if not user.generate_otp():
                    messages.error(request, 'Failed to send OTP. Please try again.')
                    return redirect(request.path)
                
                # Send email with OTP
                try:
                    subject = 'Password Reset OTP'
                    message = f'Hello {user.first_name},\n\nYour OTP for password reset is: {user.otp}\n\nValid for 10 minutes.'
                    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])
                except Exception as e:
                    logger.error(f"Failed to send password reset email: {e}")
                    messages.error(request, 'Failed to send OTP email. Please try again.')
                    return redirect(request.path)

                request.session['reset_user_id'] = user.id
                messages.success(request, 'OTP sent to your email.')
                return redirect('accounts:reset_password')

            except User.DoesNotExist:
                messages.error(request, 'No account found with this email.')
    else:
        form = ForgotPasswordForm()

    return render(request, 'accounts/forgot_password.html', {'form': form})

def reset_password(request):
    if request.method == 'POST':
        clear_messages(request)
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            otp = form.cleaned_data['otp']
            new_password = form.cleaned_data['new_password']

            user_id = request.session.get('reset_user_id')

            if not user_id:
                messages.error(request, 'Session expired.')
                return redirect('accounts:forgot_password')

            try:
                user = User.objects.get(id=user_id)

                if user.verify_otp(otp):
                    user.set_password(new_password)
                    user.clear_otp()
                    user.is_active = True
                    user.save()

                    del request.session['reset_user_id']

                    messages.success(request, 'Password reset successful!')
                    return redirect('accounts:login')
                else:
                    messages.error(request, 'Invalid or expired OTP.')

            except User.DoesNotExist:
                messages.error(request, 'User not found.')

    else:
        form = ResetPasswordForm()

    return render(request, 'accounts/reset_password.html', {'form': form})

from django.contrib.auth import update_session_auth_hash

@login_required
def change_password(request):
    if request.method == 'POST':
        clear_messages(request)
        old_password = request.POST.get('old_password')

        if not old_password:
            messages.error(request, 'Please enter your current password.')
            return redirect('accounts:change_password')

        if not request.user.check_password(old_password):
            messages.error(request, 'Incorrect current password.')
            return redirect('accounts:change_password')

        # Generate OTP for existing user
        if not request.user.generate_otp():
            messages.error(request, 'Failed to generate OTP. Please try again.')
            return redirect('accounts:change_password')
        
        # Send OTP email
        try:
            subject = 'Password Change OTP'
            message = f'Hello {request.user.first_name},\n\nYour OTP for password change is: {request.user.otp}\n\nValid for 10 minutes.'
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [request.user.email])
        except Exception as e:
            logger.error(f"Failed to send password change OTP: {e}")
            messages.error(request, 'Failed to send OTP email. Please try again.')
            return redirect('accounts:change_password')

        request.session['change_password_user_id'] = request.user.id

        messages.success(request, 'OTP sent to your registered email.')
        return redirect('accounts:verify_change_password_otp')

    return render(request, 'accounts/change_password.html')

@login_required
def verify_change_password_otp(request):
    if request.method == 'POST':
        clear_messages(request)
        otp = request.POST.get('otp')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        user_id = request.session.get('change_password_user_id')

        if not user_id:
            messages.error(request, 'Session expired. Please try again.')
            return redirect('accounts:change_password')

        if not otp:
            messages.error(request, 'Please enter the OTP.')
            return redirect('accounts:verify_change_password_otp')

        if not new_password or not confirm_password:
            messages.error(request, 'Please enter and confirm your new password.')
            return redirect('accounts:verify_change_password_otp')

        if new_password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return redirect('accounts:verify_change_password_otp')

        # 🔒 Password strength rules
        if len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return redirect('accounts:verify_change_password_otp')

        if new_password.isdigit():
            messages.error(request, 'Password cannot be entirely numeric.')
            return redirect('accounts:verify_change_password_otp')

        if new_password.lower() == new_password or new_password.upper() == new_password:
            messages.error(request, 'Password must include both uppercase and lowercase letters.')
            return redirect('accounts:verify_change_password_otp')

        try:
            user = User.objects.get(id=user_id)

            # ❗ Prevent reuse of old password
            if user.check_password(new_password):
                messages.error(request, 'New password cannot be the same as old password.')
                return redirect('accounts:verify_change_password_otp')

            if user.verify_otp(otp):
                user.set_password(new_password)
                user.clear_otp()
                user.save()

                update_session_auth_hash(request, user)

                del request.session['change_password_user_id']

                messages.success(request, 'Password changed successfully!')
                return redirect('accounts:dashboard')
            else:
                messages.error(request, 'Invalid or expired OTP.')

        except User.DoesNotExist:
            messages.error(request, 'User not found.')

    return render(request, 'accounts/verify_change_password_otp.html')

@login_required
def dashboard(request):
    user = request.user

    profile_data = None
    clear_messages(request)

    if user.role == User.Role.WHOLESELLER:
        profile_data = getattr(user, 'wholeseller_profile', None)

    elif user.role == User.Role.RESELLER:
        profile_data = getattr(user, 'reseller_profile', None)

    elif user.role == User.Role.ADMIN:
        profile_data = getattr(user, 'admin_profile', None)

    context = {
        'user': user,
        'profile': profile_data,
        'role': user.get_role_display(),
        'is_superuser': user.is_superuser
    }

    return render(request, 'accounts/dashboard.html', context)

@login_required
def logout_view(request):
    """Logout user"""
    logout(request)
    clear_messages(request)
    messages.info(request, 'You have been logged out.')
    return redirect('accounts:login')

