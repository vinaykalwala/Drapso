# shiprocket/services.py
import requests
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

class ShiprocketService:
    def __init__(self):
        self.base_url = 'https://apiv2.shiprocket.in/v1/external'
        self.email = settings.SHIPROCKET_EMAIL
        self.password = settings.SHIPROCKET_PASSWORD
        self.token = None
        self._pickup_locations_cache = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Shiprocket and get token"""
        cached_token = cache.get('shiprocket_token')
        if cached_token:
            self.token = cached_token
            logger.info("Using cached Shiprocket token")
            return True
        
        url = f"{self.base_url}/auth/login"
        payload = {
            "email": self.email,
            "password": self.password
        }
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            self.token = data.get('token')
            
            if self.token:
                cache.set('shiprocket_token', self.token, 82800)
                logger.info("Shiprocket authentication successful")
                return True
            else:
                logger.error(f"No token in response: {data}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Shiprocket authentication failed: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return False
    
    def _get_headers(self):
        """Get request headers with token"""
        if not self.token:
            self._authenticate()
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    def get_pickup_locations(self, force_refresh=False):
        """
        Get all registered pickup locations from Shiprocket API
        The API returns: {"data": {"shipping_address": [...]}}
        """
        if not force_refresh and self._pickup_locations_cache is not None:
            logger.info(f"Using cached pickup locations: {len(self._pickup_locations_cache)} locations")
            return self._pickup_locations_cache
        
        url = f"{self.base_url}/settings/company/pickup"
        
        try:
            logger.info(f"Fetching pickup locations from: {url}")
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            
            # If token expired, retry once
            if response.status_code == 401:
                logger.info("Token expired, re-authenticating...")
                self._authenticate()
                response = requests.get(url, headers=self._get_headers(), timeout=30)
            
            logger.info(f"Pickup locations API response status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    logger.debug(f"API Response structure: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")
                    
                    # Extract shipping addresses from the correct path
                    shipping_addresses = []
                    
                    # The API returns: {"data": {"shipping_address": [...]}}
                    if isinstance(data, dict) and 'data' in data:
                        data_obj = data['data']
                        if isinstance(data_obj, dict) and 'shipping_address' in data_obj:
                            shipping_addresses = data_obj['shipping_address']
                            logger.info(f"Found shipping_address array with {len(shipping_addresses)} items")
                        elif isinstance(data_obj, list):
                            shipping_addresses = data_obj
                            logger.info(f"Found data array with {len(shipping_addresses)} items")
                    
                    # Parse and format locations
                    formatted_locations = []
                    for addr in shipping_addresses:
                        if isinstance(addr, dict):
                            # Extract pickup location name (this is the tag name)
                            pickup_location_name = addr.get('pickup_location')
                            
                            # Extract pincode from address (might be in different fields)
                            pincode = (
                                addr.get('pin_code') or 
                                addr.get('pincode') or 
                                addr.get('postal_code')
                            )
                            
                            # If pincode not directly available, try to extract from address string
                            if not pincode and addr.get('address'):
                                # Try to find 6-digit pincode in address
                                import re
                                match = re.search(r'\b\d{6}\b', addr.get('address', ''))
                                if match:
                                    pincode = match.group()
                            
                            if pickup_location_name and pincode:
                                formatted_locations.append({
                                    'id': addr.get('id'),
                                    'name': pickup_location_name,
                                    'pickup_location': pickup_location_name,  # This is the tag name for API
                                    'address': addr.get('address', ''),
                                    'address_2': addr.get('address_2', ''),
                                    'city': addr.get('city', ''),
                                    'state': addr.get('state', ''),
                                    'country': addr.get('country', 'India'),
                                    'pincode': str(pincode),
                                    'phone': addr.get('phone', ''),
                                    'email': addr.get('email', ''),
                                    'is_primary': addr.get('is_primary', False),
                                    'is_active': addr.get('is_active', True),
                                })
                                logger.debug(f"Found pickup location: {pickup_location_name} (pincode: {pincode})")
                    
                    if formatted_locations:
                        self._pickup_locations_cache = formatted_locations
                        logger.info(f"Successfully fetched {len(formatted_locations)} pickup locations from API")
                        for loc in formatted_locations:
                            logger.info(f"  - {loc['name']}: pincode {loc['pincode']}")
                    else:
                        logger.warning(f"No valid pickup locations found in API response")
                        self._pickup_locations_cache = []
                    
                    return self._pickup_locations_cache
                    
                except ValueError as e:
                    logger.error(f"Failed to parse JSON response: {e}")
                    logger.error(f"Raw response: {response.text[:500]}")
                    self._pickup_locations_cache = []
                    return []
            else:
                logger.error(f"Failed to fetch pickup locations. Status: {response.status_code}")
                logger.error(f"Response: {response.text[:500]}")
                self._pickup_locations_cache = []
                return []
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error fetching pickup locations: {str(e)}")
            self._pickup_locations_cache = []
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching pickup locations: {str(e)}")
            self._pickup_locations_cache = []
            return []
    
    def get_pickup_location_by_pincode(self, pincode, preferred_nickname=None):
        """
        Find pickup location name by pincode using dynamic API data.
        
        Args:
            pincode: Pincode to search for
            preferred_nickname: The address_name from your ResellerAddress/WholesellerAddress model
        """
        pincode_str = str(pincode).strip()
        locations = self.get_pickup_locations()
        
        if not locations:
            logger.error(f"No pickup locations available in Shiprocket for pincode {pincode_str}")
            return None
        
        # Strategy 1: Match BOTH Pincode and Nickname (Highest Precision)
        if preferred_nickname:
            for loc in locations:
                if str(loc.get('pincode')) == pincode_str and loc.get('name') == preferred_nickname:
                    logger.info(f"Matched location by pincode AND nickname: {preferred_nickname}")
                    return preferred_nickname

        # Strategy 2: Match just the Nickname (If pincodes were updated)
        if preferred_nickname:
            for loc in locations:
                if loc.get('name') == preferred_nickname:
                    logger.info(f"Matched location by nickname only: {preferred_nickname}")
                    return preferred_nickname

        # Strategy 3: Match just the Pincode (Fallback)
        for loc in locations:
            if str(loc.get('pincode')) == pincode_str:
                pickup_name = loc.get('pickup_location') or loc.get('name')
                logger.info(f"Found match by pincode only: '{pickup_name}'")
                return pickup_name
        
        # Strategy 4: Use Primary if all else fails
        primary = next((loc for loc in locations if loc.get('is_primary')), None)
        if primary:
            return primary.get('name')

        return locations[0].get('name') if locations else None

    def get_pickup_nickname(self, pincode):
        """
        Fetches registered pickup locations from Shiprocket 
        and matches the nickname based on the pincode.
        """
        url = f"{self.base_url}/settings/company/pickup"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            if response.status_code == 401:
                self._authenticate()
                response = requests.get(url, headers=self._get_headers(), timeout=30)
                
            data = response.json()
            if response.status_code == 200:
                # Shiprocket returns addresses in 'data' -> 'shipping_address'
                shipping_addresses = data.get('data', {}).get('shipping_address', [])
                for addr in shipping_addresses:
                    if str(addr.get('pin_code')) == str(pincode):
                        return addr.get('pickup_location') # This is the Nickname
            
            logger.warning(f"No Shiprocket nickname found for pincode {pincode}. Using 'Primary'.")
            return "Primary" 
        except Exception as e:
            logger.error(f"Error resolving pickup nickname: {e}")
            return "Primary"

    def get_wallet_balance(self):
        """Fetches the current Shiprocket wallet balance amount"""
        url = f"{self.base_url}/settings/company/balance"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            data = response.json()
            if response.status_code == 200:
                return float(data.get('data', {}).get('balance_amount', 0))
            return 0.0
        except Exception:
            return 0.0

    def calculate_shipping_charge(self, pickup_postcode, delivery_postcode, weight, pickup_location, length=10, breadth=10, height=10):
        """
        Calculate shipping using Billable Weight and Package Dimensions.
        """
        url = f"{self.base_url}/courier/serviceability"
        params = {
            "pickup_postcode": pickup_postcode,
            "delivery_postcode": delivery_postcode,
            "weight": weight,
            "length": length,
            "breadth": breadth,
            "height": height,
            "cod": 0,
            "pickup_location": pickup_location
        }
        
        try:
            response = requests.get(url, headers=self._get_headers(), params=params, timeout=30)
            if response.status_code == 401:
                self._authenticate()
                response = requests.get(url, headers=self._get_headers(), params=params, timeout=30)
                
            data = response.json()
            if response.status_code == 200 and data.get('status') == 200:
                couriers = data.get('data', {}).get('available_courier_companies', [])
                if couriers:
                    couriers.sort(key=lambda x: float(x.get('rate', 9999)))
                    cheapest = couriers[0]
                    return {
                        'shipping_charge': float(cheapest.get('rate')),
                        'delivery_time': cheapest.get('etd', '4-7 days'),
                        'courier_name': cheapest.get('courier_name'),
                        'courier_company_id': cheapest.get('courier_company_id'), 
                        'estimated_weight': cheapest.get('weight')
                    }
            
            error_msg = data.get('message', 'No couriers available for this route.')
            logger.warning(f"Shiprocket Serviceability failure: {error_msg}")
            return None
        except Exception as e:
            logger.error(f"Serviceability API call failed: {str(e)}")
            return None
    def sync_order_statuses(self, shiprocket_ids):
        """Fetch latest tracking/status for multiple orders at once"""
        url = f"{self.base_url}/orders/show/adhoc"
        # Shiprocket allows checking multiple IDs at once
        params = {"ids[]": shiprocket_ids} 
        
        try:
            response = requests.get(url, headers=self._get_headers(), params=params)
            if response.status_code == 200:
                return response.json().get('data', [])
            return []
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return []

    def get_cheapest_courier(self, pickup_postcode, delivery_postcode, weight, length, breadth, height):
        url = f"{self.base_url}/courier/serviceability/"
        params = {
            'pickup_postcode': pickup_postcode,
            'delivery_postcode': delivery_postcode,
            'weight': weight,
            'cod': 0, # Prepaid
            'length': length, 'breadth': breadth, 'height': height,
        }
        try:
            res = requests.get(url, headers=self._get_headers(), params=params)
            data = res.json()
            
            if res.status_code == 200 and data.get('status') == 200:
                couriers = data['data']['available_courier_companies']
                if couriers:
                    # Logic: Find the cheapest available courier
                    cheapest = min(couriers, key=lambda x: float(x['freight_charge']))
                    return {
                        'courier_id': cheapest['courier_company_id'],
                        'courier_name': cheapest['courier_name'],
                        'etd': cheapest['etd'] or "4-6 Days",
                        'cost': cheapest['freight_charge']
                    }
            else:
                logger.error(f"Shiprocket Serviceability Failed: {data}")
            return None
        except Exception as e:
            logger.exception("Shiprocket API Connection Error")
            return None

    def create_order(self, order_data):
        url = f"{self.base_url}/orders/create/adhoc"
        
        # Address Guard: Ensure address is at least 3 chars by padding with city if needed
        raw_address = order_data.get('address', '')
        if len(raw_address) < 3:
            clean_address = f"{raw_address}, {order_data.get('city')}"[:80]
        else:
            clean_address = raw_address[:80]

        # Prepare items payload
        order_items = [{
            "name": item.get('name')[:40],
            "sku": item.get('sku'),
            "units": int(item.get('units', 1)),
            "selling_price": float(item.get('selling_price', 0)),
        } for item in order_data.get('items', [])]

        payload = {
            "order_id": str(order_data.get('order_id')),
            "order_date": order_data.get('order_date'),
            "pickup_location": order_data.get('pickup_location'), 
            "billing_customer_name": order_data.get('customer_name'),
            "billing_last_name": "",
            "billing_address": clean_address, # Used protected address
            "billing_city": order_data.get('city'),
            "billing_pincode": order_data.get('pincode'),
            "billing_state": order_data.get('state'),
            "billing_country": "India",
            "billing_email": order_data.get('email'),
            "billing_phone": str(order_data.get('phone'))[-10:], 
            "shipping_is_billing": True,
            "order_items": order_items,
            "payment_method": "Prepaid",
            "sub_total": float(order_data.get('sub_total')),
            "shipping_charges": float(order_data.get('shipping_charges', 0)),
            "total": float(order_data.get('total')),
            "weight": float(order_data.get('weight', 0.5)),
            "length": float(order_data.get('length', 10)),
            "breadth": float(order_data.get('breadth', 10)),
            "height": float(order_data.get('height', 10)),
        }

        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            data = response.json()
            if response.status_code in [200, 201] and data.get('order_id'):
                return {
                    'success': True,
                    'shiprocket_order_id': data.get('order_id'),
                    'shipment_id': data.get('shipment_id')
                }
            return {'success': False, 'error': data.get('message'), 'details': data.get('errors')}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def assign_awb(self, shipment_id, courier_id=None):
        url = f"{self.base_url}/courier/assign/awb"
        payload = {"shipment_id": shipment_id}
        if courier_id:
            payload["courier_id"] = int(courier_id)

        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            data = response.json()
            
            if response.status_code == 200 and data.get('awb_assign_status') == 1:
                res_data = data.get('response', {}).get('data', {})
                return {
                    'success': True,
                    'awb_code': res_data.get('awb_code'),
                    'courier_name': res_data.get('courier_name'),
                    'actual_charge': res_data.get('rate') # This raw value is protected by the view's math
                }
            
            error_reason = data.get('message', 'AWB Assignment Failed')
            return {'success': False, 'error': error_reason}
        except Exception as e:
            return {'success': False, 'error': str(e)}
            
    def generate_shipping_label(self, shipment_id):
        url = f"{self.base_url}/courier/generate/label"

        payload = {
            "shipment_id": [int(shipment_id)]  # ✅ MUST be array
        }

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=30
            )


            data = response.json()

            # ✅ Extract label URL from all possible formats
            label_url = (
                data.get('label_url') or
                data.get('response', {}).get('label_url')
            )

            if response.status_code == 200 and label_url:
                return {
                    'success': True,
                    'label_url': label_url
                }

            return {
                'success': False,
                'error': data
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    def generate_invoice(self, shiprocket_order_id):
        """Generate invoice for Shiprocket Order IDs"""
        url = f"{self.base_url}/orders/print/invoice"
        payload = {"ids": [shiprocket_order_id]}
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            data = response.json()
            if response.status_code == 200 and data.get('is_invoice_created'):
                return {'success': True, 'url': data.get('invoice_url'), 'invoice_url': data.get('invoice_url')}
            return {'success': False, 'error': 'Invoice generation failed or not ready'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def generate_manifest(self, shipment_id):
        """Generate manifest for Shipment IDs"""
        url = f"{self.base_url}/manifests/generate"
        payload = {"shipment_id": [shipment_id]}
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            data = response.json()
            if response.status_code == 200 and data.get('manifest_url'):
                return {'success': True, 'url': data.get('manifest_url'), 'manifest_url': data.get('manifest_url')}
            return {'success': False, 'error': 'Manifest not ready. Ensure pickup is requested.'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def request_pickup(self, shipment_id):
        """Trigger the courier pickup request"""
        url = f"{self.base_url}/courier/generate/pickup"
        payload = {"shipment_id": [shipment_id]}
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            data = response.json()
            return {'success': response.status_code == 200, 'data': data, 'error': data.get('message')}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    def cancel_shipment(self, awb_code):
        """
        Triggers the AWB cancellation in Shiprocket.
        """
        url = f"{self.base_url}/courier/generate/cancel"
        # Shiprocket expects a list of AWBs
        payload = {"awbs": [awb_code]} 
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            data = response.json()
            # Status 200 means the request was accepted
            if response.status_code == 200:
                return {'success': True, 'message': 'Cancellation requested successfully'}
            return {'success': False, 'error': data.get('message', 'Cancellation failed')}
        except Exception as e:
            return {'success': False, 'error': str(e)}
            
    def create_return_order(self, return_data):
        """Create a return shipment for reverse pickup"""
        url = f"{self.base_url}/returns/create"
        
        # Get pickup location for return (where the return will be received)
        pickup_location = return_data.get('pickup_location')
        if pickup_location and str(pickup_location).isdigit() and len(str(pickup_location)) in [5, 6]:
            location_name = self.get_pickup_location_by_pincode(pickup_location)
            if location_name:
                pickup_location = location_name
        
        # Prepare return items
        return_items = []
        for item in return_data.get('items', []):
            return_items.append({
                "name": item.get('name', 'Product'),
                "quantity": int(item.get('quantity', 1)),
                "price": float(item.get('price', 0))
            })
        
        payload = {
            "order_id": return_data.get('order_id'),
            "return_order_id": f"RET{return_data.get('order_id')}",
            "pickup_location": pickup_location,
            "customer_name": return_data.get('customer_name'),
            "customer_address": return_data.get('address'),
            "customer_city": return_data.get('city'),
            "customer_state": return_data.get('state'),
            "customer_pincode": return_data.get('pincode'),
            "customer_phone": return_data.get('phone'),
            "return_items": return_items,
            "weight": float(return_data.get('weight', 0.5)),
            "length": float(return_data.get('length', 10)),
            "breadth": float(return_data.get('breadth', 10)),
            "height": float(return_data.get('height', 10)),
            "is_replacement": return_data.get('is_replacement', False),
            "pickup_date": return_data.get('pickup_date')
        }
        
        logger.info(f"Creating return order for: {return_data.get('order_id')}")
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            
            if response.status_code == 401:
                logger.info("Token expired, re-authenticating...")
                self._authenticate()
                response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"Return order created: {data.get('shipment_id')}")
            
            return {
                'success': True,
                'return_awb': data.get('awb_code'),
                'return_shipment_id': data.get('shipment_id'),
                'label_url': data.get('label_url'),
                'courier_name': data.get('courier_name'),
                'pickup_scheduled': data.get('pickup_scheduled_date')
            }
            
        except Exception as e:
            logger.error(f"Return order creation failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def schedule_return_pickup(self, return_shipment_id, pickup_date=None):
        """Schedule pickup for a return shipment"""
        url = f"{self.base_url}/returns/pickup/schedule"
        
        if not pickup_date:
            pickup_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        payload = {
            "shipment_id": return_shipment_id,
            "pickup_date": pickup_date
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            
            if response.status_code == 401:
                logger.info("Token expired, re-authenticating...")
                self._authenticate()
                response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            
            response.raise_for_status()
            data = response.json()
            logger.info(f"Return pickup scheduled for {pickup_date}")
            return data
            
        except Exception as e:
            logger.error(f"Return pickup scheduling failed: {str(e)}")
            return None
    
    def get_all_shiprocket_orders(self, page=1, per_page=50):
        """Fetch all orders directly from Shiprocket API"""
        url = f"{self.base_url}/orders"
        params = {
            "page": page,
            "per_page": per_page,
            # You can add status filters here if needed
        }
        
        try:
            response = requests.get(url, headers=self._get_headers(), params=params, timeout=30)
            if response.status_code == 200:
                return response.json() # Returns a dict with 'data' (list of orders)
            return {"data": []}
        except Exception as e:
            logger.error(f"Failed to fetch Shiprocket orders: {e}")
            return {"data": []}