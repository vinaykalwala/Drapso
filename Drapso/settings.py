"""
Django settings for Drapso project.
"""

from pathlib import Path
import os

# =========================================================
# BASE DIRECTORY
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

# =========================================================
# SECURITY
# =========================================================

SECRET_KEY = 'django-insecure-vqvxd4d@jphz6o_p0)s$zq90tlh^d%er-2b$s3p483jk=7$8bi'

DEBUG = False

ALLOWED_HOSTS = [
    '.drapso.com',
    'drapso.com',
    'www.drapso.com',
    '18.61.74.84',
    'localhost',
    '127.0.0.1',
]

CSRF_TRUSTED_ORIGINS = [
    'https://drapso.com',
    'https://www.drapso.com',
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

USE_X_FORWARDED_HOST = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_SSL_REDIRECT = False

# =========================================================
# DJANGO DEFAULTS
# =========================================================

DATA_UPLOAD_MAX_NUMBER_FIELDS = 10240
MAX_UPLOAD_SIZE = 5242880

# =========================================================
# INSTALLED APPS
# =========================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'general',
    'accounts',
    'wholesellers',
    'resellers',
    'products',
    'theme_manager',
    'orders',
    'shiprocket',
    'settlement',
    'analytics',
]

# =========================================================
# MIDDLEWARE
# =========================================================

MIDDLEWARE = [

    'django.middleware.security.SecurityMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',

    'resellers.middleware.SubdomainMiddleware',
    'resellers.middleware.StoreContextMiddleware',

    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',

    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',

    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# =========================================================
# URLS
# =========================================================

ROOT_URLCONF = 'Drapso.urls'

# =========================================================
# TEMPLATES
# =========================================================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',

        'DIRS': [
            os.path.join(BASE_DIR, 'templates')
        ],

        'APP_DIRS': True,

        'OPTIONS': {
            'context_processors': [

                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',

                'accounts.context_processors.user_profile_data',
                'resellers.context_processors.store_context',
                'general.context_processors.global_settings',
            ],
        },
    },
]

# =========================================================
# WSGI
# =========================================================

WSGI_APPLICATION = 'Drapso.wsgi.application'

# =========================================================
# DATABASE
# =========================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# =========================================================
# PASSWORD VALIDATORS
# =========================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# =========================================================
# INTERNATIONALIZATION
# =========================================================

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Kolkata'

USE_I18N = True

USE_TZ = True

# =========================================================
# STATIC FILES
# =========================================================

STATIC_URL = 'static/'

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static')
]

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# =========================================================
# MEDIA FILES
# =========================================================

MEDIA_URL = '/media/'

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# =========================================================
# AUTH USER
# =========================================================

AUTH_USER_MODEL = 'accounts.User'

AUTHENTICATION_BACKENDS = [
    'accounts.backends.EmailOrUsernameBackend',
]

# =========================================================
# LOGIN / LOGOUT
# =========================================================

LOGIN_URL = 'accounts:login'

LOGIN_REDIRECT_URL = 'accounts:dashboard'

LOGOUT_REDIRECT_URL = 'home'

# =========================================================
# RAZORPAY
# =========================================================

RAZORPAY_KEY_ID = 'rzp_test_SipGv44QRSqWtJ'

RAZORPAY_KEY_SECRET = 'KrYQ0wqvkybDSnuNgKGVMRW5'

RAZORPAY_CURRENCY = 'INR'

RAZORPAYX_ACCOUNT_NUMBER = '2323230032242076'

SUBSCRIPTION_CURRENCY = "INR"

# =========================================================
# EMAIL
# =========================================================

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

EMAIL_HOST = 'smtp.gmail.com'

EMAIL_PORT = 587

EMAIL_USE_TLS = True

EMAIL_HOST_USER = 'mkdrapso@gmail.com'

EMAIL_HOST_PASSWORD = 'aeer vmzd cbnr lpeo'

DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# =========================================================
# CACHE
# =========================================================

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "otp-rate-limit",
    }
}

# =========================================================
# SHIPROCKET
# =========================================================
MAIN_DOMAIN = "https://drapso.com"

SHIPROCKET_EMAIL = 'dandugulamanojkumar@gmail.com'

SHIPROCKET_PASSWORD = 'rGe&NvTK@Xw9e@n&Ltbul1bTL8CIBKiE'

SHIPROCKET_BASE_URL = 'https://apiv2.shiprocket.in/v1/external'

SHIPROCKET_WEBHOOK_SECRET = ''
