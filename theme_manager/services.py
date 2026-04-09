# theme_manager/services.py
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import ThemeSwitchSession, ArchivedProductRecord, RestoreBatch, ThemeSwitchHistory

class ThemeSwitchService:
    """Handles theme switching with data preservation"""
    
    def __init__(self, store, request=None):
        self.store = store
        self.store_id = store.id
        self.reseller_id = store.reseller_id
        self.request = request
    
    def can_switch_to(self, target_theme):
        """Check if switch is allowed"""
        
        session, _ = ThemeSwitchSession.objects.get_or_create(
            store_id=self.store_id,
            defaults={'reseller_id': self.reseller_id}
        )
        
        if session.current_theme == target_theme:
            return False, f"Already on {target_theme} theme"
        
        current_month = timezone.now().strftime('%Y-%m')
        if session.switch_month != current_month:
            session.switch_count_month = 0
            session.switch_month = current_month
        
        plan = self.store.subscription_plan
        max_switches = getattr(plan, 'max_theme_switches_per_month', 3) if plan else 3
        
        if session.switch_count_month >= max_switches:
            return False, f"Monthly switch limit reached ({max_switches} switches)"
        
        return True, "OK"
    
    def get_switch_impact(self, target_theme):
        """Calculate impact before switching"""
        from products.models import ResellerProduct
        
        active_products = ResellerProduct.objects.filter(
            store_id=self.store_id,
            is_active=True
        )
        current_count = active_products.count()
        
        if target_theme == 'single':
            products_to_archive = max(0, current_count - 1)
            
            # Suggest which product to keep
            keep_product = None
            if current_count > 0:
                keep_product = active_products.filter(is_featured=True).first()
                if not keep_product:
                    keep_product = active_products.order_by('-created_at').first()
            
            return {
                'will_archive': products_to_archive > 0,
                'products_to_archive': products_to_archive,
                'products_to_keep': 1,
                'current_count': current_count,
                'suggested_keep_product': {
                    'id': keep_product.id,
                    'name': keep_product.name
                } if keep_product else None,
                'warning': f"You will lose {products_to_archive} product(s) temporarily." if products_to_archive > 0 else None
            }
        else:
            session = ThemeSwitchSession.objects.filter(store_id=self.store_id).first()
            archived_count = ArchivedProductRecord.objects.filter(
                store=self.store,
                is_restorable=True
            ).count()
            
            plan_limit = self._get_multi_theme_limit()
            available_slots = max(0, plan_limit - current_count)
            
            return {
                'will_restore': archived_count > 0,
                'archived_count': archived_count,
                'plan_limit': plan_limit,
                'current_count': current_count,
                'available_slots': available_slots,
                'can_restore_all': available_slots >= archived_count,
                'warning': f"You have {archived_count} archived product(s)." if archived_count > 0 else None
            }
    
    @transaction.atomic
    def switch_to_single_theme(self, keep_product_id=None):
        """Switch to single theme - archive all but one product"""
        from products.models import ResellerProduct
        
        session, _ = ThemeSwitchSession.objects.get_or_create(
            store_id=self.store_id,
            defaults={'reseller_id': self.reseller_id}
        )
        
        active_products = ResellerProduct.objects.filter(
            store_id=self.store_id,
            is_active=True
        )
        
        products_before = active_products.count()
        products_archived = 0
        
        # Determine which product to keep
        if keep_product_id:
            keep_product = active_products.filter(id=keep_product_id).first()
        else:
            keep_product = active_products.filter(is_featured=True).first()
            if not keep_product:
                keep_product = active_products.order_by('-created_at').first()
        
        # Archive products
        for product in active_products:
            if keep_product and product.id == keep_product.id:
                session.active_product_id = product.id
                continue
            
            # Create archive record
            ArchivedProductRecord.objects.create(
                product=product,
                store=self.store,
                archive_reason='theme_switch',
                restore_priority=self._calculate_priority(product)
            )
            products_archived += 1
            
            # Deactivate product (preserve all other fields including is_published)
            product.is_active = False
            product.save(update_fields=['is_active', 'updated_at'])
        
        # Update session
        session.current_theme = 'single'
        session.last_switch_at = timezone.now()
        session.switch_count_month += 1
        session.save()
        
        # Log history
        ThemeSwitchHistory.objects.create(
            store_id=self.store_id,
            reseller_id=self.reseller_id,
            from_theme='multiple',
            to_theme='single',
            products_active_before=products_before,
            products_active_after=1,
            products_archived=products_archived,
            products_restored=0,
            reason='manual',
            ip_address=self._get_ip()
        )
        
        return {
            'success': True,
            'kept_product_id': keep_product.id if keep_product else None,
            'archived_count': products_archived
        }
    
    @transaction.atomic
    def switch_to_multi_theme(self, product_ids=None, restore_all=False):
        """Switch to multi theme - restore archived products"""
        from products.models import ResellerProduct
        
        session = ThemeSwitchSession.objects.get(store_id=self.store_id)
        
        plan_limit = self._get_multi_theme_limit()
        current_active = ResellerProduct.objects.filter(
            store_id=self.store_id,
            is_active=True
        ).count()
        
        available_slots = max(0, plan_limit - current_active)
        
        # Get products to restore
        archived_products = ArchivedProductRecord.objects.filter(
            store=self.store,
            is_restorable=True
        ).select_related('product')
        
        if restore_all:
            products_to_restore = archived_products.order_by('-restore_priority')[:available_slots]
        elif product_ids:
            products_to_restore = archived_products.filter(product_id__in=product_ids)
        else:
            products_to_restore = archived_products.none()
        
        products_restored = 0
        
        for archive_record in products_to_restore:
            # Restore preserves all original data including is_published
            archive_record.restore()
            products_restored += 1
        
        # Update session
        session.current_theme = 'multiple'
        session.active_product_id = None
        session.last_switch_at = timezone.now()
        session.save()
        
        # Log history
        ThemeSwitchHistory.objects.create(
            store_id=self.store_id,
            reseller_id=self.reseller_id,
            from_theme='single',
            to_theme='multiple',
            products_active_before=current_active,
            products_active_after=current_active + products_restored,
            products_archived=0,
            products_restored=products_restored,
            reason='manual',
            ip_address=self._get_ip()
        )
        
        return {
            'success': True,
            'restored_count': products_restored,
            'available_slots': available_slots - products_restored,
            'remaining_archived': ArchivedProductRecord.objects.filter(store=self.store).count()
        }
    
    def _calculate_priority(self, product):
        """Calculate restore priority score"""
        score = 0
        if product.is_featured:
            score += 100
        if product.is_published:
            score += 50
        if hasattr(product, 'total_sales'):
            score += min(int(product.total_sales or 0), 1000)
        score += (timezone.now() - product.created_at).days // 30
        return score
    
    def _get_multi_theme_limit(self):
        """Get multi theme product limit from subscription plan"""
        plan = self.store.subscription_plan
        if plan:
            return getattr(plan, 'multiple_theme_limit', 50)
        return 50
    
    def _get_ip(self):
        if self.request:
            x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                return x_forwarded_for.split(',')[0]
            return self.request.META.get('REMOTE_ADDR')
        return None


class RestorationService:
    """Handles product restoration with plan limit checking"""
    
    def __init__(self, store, user):
        self.store = store
        self.user = user
        self.store_id = store.id
    
    def get_restoration_capacity(self):
        """Calculate how many products can be restored"""
        from products.models import ResellerProduct
        
        plan = self.store.subscription_plan
        
        if not plan:
            return {
                'has_plan': False,
                'max_allowed': 0,
                'current_active': 0,
                'available_slots': 0,
                'can_restore_any': False,
                'message': 'No active subscription plan'
            }
        
        session = ThemeSwitchSession.objects.filter(store_id=self.store_id).first()
        current_theme = session.current_theme if session else 'multiple'
        
        if current_theme == 'single':
            max_allowed = 1
        else:
            max_allowed = getattr(plan, 'multiple_theme_limit', 50)
        
        current_active = ResellerProduct.objects.filter(
            store_id=self.store_id,
            is_active=True
        ).count()
        
        available_slots = max(0, max_allowed - current_active)
        
        archived_count = ArchivedProductRecord.objects.filter(
            store=self.store,
            is_restorable=True
        ).count()
        
        return {
            'has_plan': True,
            'plan_name': plan.get_name_display() if hasattr(plan, 'get_name_display') else plan.name,
            'plan_limit': max_allowed,
            'current_active': current_active,
            'available_slots': available_slots,
            'archived_count': archived_count,
            'can_restore_any': available_slots > 0 and archived_count > 0,
            'can_restore_all': available_slots >= archived_count,
            'message': self._get_capacity_message(available_slots, archived_count)
        }
    
    def _get_capacity_message(self, available_slots, archived_count):
        if available_slots == 0:
            return "Your store has reached its product limit. Upgrade your plan to add more products."
        elif available_slots >= archived_count:
            return f"You can restore all {archived_count} archived product(s)."
        else:
            return f"You can restore {available_slots} of {archived_count} archived product(s). Upgrade your plan to restore more."
    
    def get_restorable_products(self, filters=None, sort_by='-restore_priority'):
        """Get archived products with their published status"""
        archived_records = ArchivedProductRecord.objects.filter(
            store=self.store,
            is_restorable=True
        ).select_related('product')
        
        if filters:
            if filters.get('search'):
                archived_records = archived_records.filter(
                    product__name__icontains=filters['search']
                )
            
            if filters.get('min_price'):
                archived_records = archived_records.filter(
                    product__selling_price__gte=filters['min_price']
                )
            
            if filters.get('max_price'):
                archived_records = archived_records.filter(
                    product__selling_price__lte=filters['max_price']
                )
            
            if filters.get('published_only'):
                archived_records = archived_records.filter(product__is_published=True)
            
            if filters.get('draft_only'):
                archived_records = archived_records.filter(product__is_published=False)
        
        sort_options = {
            'price_high': '-product__selling_price',
            'price_low': 'product__selling_price',
            'name_asc': 'product__name',
            'published_first': '-product__is_published',
            '-restore_priority': '-restore_priority',
            '-archived_at': '-archived_at',
        }
        
        order_by = sort_options.get(sort_by, '-restore_priority')
        archived_records = archived_records.order_by(order_by)
        
        return archived_records
    
    def validate_restoration(self, product_ids):
        """Validate if products can be restored"""
        from products.models import ResellerProduct
        
        capacity = self.get_restoration_capacity()
        
        if not capacity['can_restore_any']:
            return {
                'valid': False,
                'error': capacity['message'],
                'can_restore_count': 0
            }
        
        products_to_restore = ArchivedProductRecord.objects.filter(
            store=self.store,
            product_id__in=product_ids,
            is_restorable=True
        ).select_related('product')
        
        requested_count = products_to_restore.count()
        
        if requested_count == 0:
            return {
                'valid': False,
                'error': 'No valid archived products selected',
                'can_restore_count': 0
            }
        
        available_slots = capacity['available_slots']
        
        if requested_count > available_slots:
            return {
                'valid': False,
                'error': f'Cannot restore {requested_count} products. Only {available_slots} slots available.',
                'can_restore_count': available_slots,
                'requested_count': requested_count,
                'excess_count': requested_count - available_slots
            }
        
        # Check for duplicates
        duplicates = []
        for record in products_to_restore:
            product = record.product
            existing = ResellerProduct.objects.filter(
                store=self.store,
                is_active=True,
                name=product.name
            ).exclude(id=product.id).first()
            
            if existing:
                duplicates.append({
                    'product_id': product.id,
                    'product_name': product.name,
                    'existing_product_id': existing.id,
                    'existing_published': existing.is_published
                })
        
        return {
            'valid': len(duplicates) == 0,
            'can_restore_count': requested_count - len(duplicates),
            'requested_count': requested_count,
            'products': products_to_restore,
            'duplicates': duplicates,
            'error': f'{len(duplicates)} product(s) already exist in your store' if duplicates else None
        }
    
    @transaction.atomic
    def restore_products(self, product_ids, restore_all=False):
        """Restore selected archived products"""
        from products.models import ResellerProduct
        
        capacity = self.get_restoration_capacity()
        
        if not capacity['can_restore_any']:
            raise ValidationError(capacity['message'])
        
        if restore_all:
            archived_records = ArchivedProductRecord.objects.filter(
                store=self.store,
                is_restorable=True
            ).order_by('-restore_priority')
            product_ids = [record.product_id for record in archived_records[:capacity['available_slots']]]
        else:
            if len(product_ids) > capacity['available_slots']:
                raise ValidationError(f'Cannot restore {len(product_ids)} products. Only {capacity["available_slots"]} slots available.')
        
        batch = RestoreBatch.objects.create(
            store=self.store,
            created_by=self.user,
            selected_product_ids=product_ids,
            plan_name_at_restore=capacity.get('plan_name', ''),
            plan_limit_at_restore=capacity['plan_limit'],
            active_products_at_restore=capacity['current_active'],
            status='processing'
        )
        
        restored = []
        skipped = []
        failed = []
        
        for product_id in product_ids:
            try:
                archive_record = ArchivedProductRecord.objects.get(
                    store=self.store,
                    product_id=product_id,
                    is_restorable=True
                )
                
                product = archive_record.product
                
                if product.is_active:
                    skipped.append({
                        'product_id': product_id,
                        'product_name': product.name,
                        'reason': 'Product is already active',
                        'published_status': product.is_published
                    })
                    continue
                
                duplicate = ResellerProduct.objects.filter(
                    store=self.store,
                    is_active=True,
                    name=product.name
                ).exclude(id=product.id).first()
                
                if duplicate:
                    skipped.append({
                        'product_id': product_id,
                        'product_name': product.name,
                        'reason': f'Product with same name already exists (ID: {duplicate.id})',
                        'published_status': product.is_published
                    })
                    continue
                
                # Restore preserves all original data including is_published
                product.is_active = True
                product.save(update_fields=['is_active', 'updated_at'])
                
                restored.append({
                    'product_id': product_id,
                    'product_name': product.name,
                    'product_price': float(product.selling_price),
                    'was_published': product.is_published,
                    'published_status': 'Published' if product.is_published else 'Draft'
                })
                
                archive_record.delete()
                
            except ArchivedProductRecord.DoesNotExist:
                failed.append({'product_id': product_id, 'reason': 'Archive record not found'})
            except Exception as e:
                failed.append({'product_id': product_id, 'reason': str(e)})
        
        batch.restored_count = len(restored)
        batch.skipped_count = len(skipped)
        batch.failed_count = len(failed)
        batch.skipped_items = skipped
        batch.failed_items = failed
        batch.status = 'completed' if len(failed) == 0 else 'partial' if len(restored) > 0 else 'failed'
        batch.completed_at = timezone.now()
        batch.save()
        
        return {
            'success': len(restored) > 0,
            'batch_id': batch.id,
            'restored': restored,
            'skipped': skipped,
            'failed': failed,
            'restored_count': len(restored),
            'skipped_count': len(skipped),
            'failed_count': len(failed),
            'remaining_capacity': capacity['available_slots'] - len(restored),
            'message': self._get_restoration_message(restored, skipped, failed, capacity)
        }
    
    def _get_restoration_message(self, restored, skipped, failed, capacity):
        parts = []
        if restored:
            published_count = sum(1 for r in restored if r.get('was_published', False))
            draft_count = len(restored) - published_count
            parts.append(f"✅ Restored {len(restored)} product(s) ({published_count} published, {draft_count} draft)")
        if skipped:
            parts.append(f"⚠️ Skipped {len(skipped)} product(s)")
        if failed:
            parts.append(f"❌ Failed to restore {len(failed)} product(s)")
        remaining = capacity['available_slots'] - len(restored)
        if remaining > 0:
            parts.append(f"📦 {remaining} slot(s) remaining")
        else:
            parts.append(f"📦 Store at limit ({capacity['plan_limit']})")
        return " | ".join(parts)