# orders/utils.py or inside your calculate_shipping view

def get_origin_pincode(product):
    """
    Determines if the shipment starts from a Wholeseller warehouse 
    or the Reseller's own location.
    """
    # 1. Check if it's an imported product (Wholeseller is the origin)
    if product.source_type == 'imported' and product.source_product:
        wholeseller_user = product.source_product.wholeseller
        address = WholesellerAddress.objects.filter(
            user=wholeseller_user, 
            is_primary=True, 
            is_active=True
        ).first()
        if address:
            return address.postal_code

    # 2. If not imported, it's the Reseller's own product
    # The reseller is the owner of the store the product is in
    reseller_user = product.store.reseller
    address = ResellerAddress.objects.filter(
        user=reseller_user, 
        is_primary=True
    ).first()
    
    if address:
        return address.postal_code
    
    return None