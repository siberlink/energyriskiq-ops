#!/usr/bin/env python3
"""
Seed script to create Stripe products and prices for EnergyRiskIQ plans.
Run this script manually to create products in Stripe.

Usage:
    python -m src.billing.seed_products
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.billing.stripe_client import init_stripe, ensure_stripe_initialized
from src.db.db import get_cursor
import stripe
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PLANS = [
    {
        "plan_code": "personal",
        "name": "Personal",
        "description": "Perfect for individual energy traders and analysts",
        "price_eur": 995,
        "features": [
            "2 alert types",
            "2 regions",
            "4 email alerts/day"
        ]
    },
    {
        "plan_code": "trader",
        "name": "Trader",
        "description": "For active traders needing real-time intelligence",
        "price_eur": 2900,
        "features": [
            "3 alert types",
            "3 regions",
            "8 email alerts/day",
            "Telegram alerts"
        ]
    },
    {
        "plan_code": "pro",
        "name": "Pro",
        "description": "Complete risk intelligence for professionals",
        "price_eur": 4900,
        "features": [
            "All alert types",
            "Unlimited regions",
            "15 email alerts/day",
            "Telegram + SMS alerts",
            "Daily digest"
        ]
    },
    {
        "plan_code": "enterprise",
        "name": "Enterprise",
        "description": "Enterprise-grade risk intelligence with priority support",
        "price_eur": 12900,
        "features": [
            "All alert types",
            "Unlimited regions",
            "30 email alerts/day",
            "All delivery channels",
            "Priority processing",
            "Custom thresholds"
        ]
    }
]


def create_products_and_prices():
    init_stripe()
    logger.info("Creating Stripe products and prices...")
    
    created = []
    
    for plan in PLANS:
        existing = stripe.Product.search(
            query=f"metadata['plan_code']:'{plan['plan_code']}'"
        )
        
        if existing.data:
            logger.info(f"Product for {plan['plan_code']} already exists: {existing.data[0].id}")
            product = existing.data[0]
        else:
            product = stripe.Product.create(
                name=f"EnergyRiskIQ {plan['name']}",
                description=plan["description"],
                metadata={
                    "plan_code": plan["plan_code"],
                    "features": ", ".join(plan["features"])
                }
            )
            logger.info(f"Created product: {product.id} for {plan['plan_code']}")
        
        prices = stripe.Price.list(product=product.id, active=True)
        monthly_price = None
        
        for price in prices.data:
            if (price.unit_amount == plan["price_eur"] and 
                price.currency == "eur" and 
                price.recurring and 
                price.recurring.interval == "month"):
                monthly_price = price
                logger.info(f"Price already exists for {plan['plan_code']}: {price.id}")
                break
        
        if not monthly_price:
            monthly_price = stripe.Price.create(
                product=product.id,
                unit_amount=plan["price_eur"],
                currency="eur",
                recurring={"interval": "month"},
                metadata={"plan_code": plan["plan_code"]}
            )
            logger.info(f"Created price: {monthly_price.id} for {plan['plan_code']} ({plan['price_eur']/100} EUR)")
        
        with get_cursor() as cur:
            cur.execute("""
                UPDATE plan_settings 
                SET stripe_product_id = %s, stripe_price_id = %s
                WHERE plan_code = %s
            """, (product.id, monthly_price.id, plan["plan_code"]))
        
        created.append({
            "plan_code": plan["plan_code"],
            "product_id": product.id,
            "price_id": monthly_price.id,
            "amount": plan["price_eur"]
        })
    
    logger.info("Stripe products and prices created successfully!")
    for item in created:
        logger.info(f"  {item['plan_code']}: product={item['product_id']}, price={item['price_id']}")
    
    return created


if __name__ == "__main__":
    create_products_and_prices()
