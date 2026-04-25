from django.contrib import admin
from .models import *

admin.site.register(WithdrawalRequest)
admin.site.register(Wallet)
admin.site.register(WalletTransaction)
admin.site.register(OrderSettlement)
