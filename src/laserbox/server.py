"""
LaserBox MCP Server

CNC business management tools with enforced workflows.
Designed for agent use — validates business rules before API calls.

Environment Variables:
    LB_URL: LaserBox API URL (default: http://100.120.238.37:4000)
    LB_USER: User identifier for API tracking (default: mcp@laserbox.local)
"""

import os
import logging
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from laserbox.client import (
    LaserBoxClient,
    LaserBoxError,
    ValidationError,
    NotFoundError,
)

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "laserbox-mcp.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

LB_URL = os.environ.get("LB_URL", "http://100.120.238.37:4000")
LB_USER = os.environ.get("LB_USER", "mcp@laserbox.local")

mcp = FastMCP(
    "LaserBox",
    instructions="""LaserBox CNC management tools with enforced workflows.

    BUSINESS RULES (strictly enforced):
    1. Customer creation REQUIRES: name. Phone is optional (omit if not available).
    2. Quotes must be created BEFORE orders
    3. Quotes must be APPROVED before converting to orders
    4. Payments require a valid order_id

    WORKFLOW: customer → quote → approve → order → payment

    QUOTE ITEMS: Each item supports unitPriceCents (price in cents). If omitted, defaults to 0.
    Use update_quote(quote_id, items=[...]) to set or update prices after creation.

    PDF EXPORTS:
    - Quote PDF: export_quote_pdf(quote_id)
    - Remision PDF: export_remision_pdf(order_id)
    """
)


def _get_client() -> LaserBoxClient:
    return LaserBoxClient(base_url=LB_URL, user=LB_USER)


def _handle_error(e: Exception) -> dict:
    if isinstance(e, ValidationError):
        return {"error": "Workflow violation", "details": str(e)}
    elif isinstance(e, NotFoundError):
        return {"error": "Not found", "details": str(e)}
    elif isinstance(e, LaserBoxError):
        return {"error": "LaserBox error", "details": str(e)}
    return {"error": "Unexpected error", "details": str(e)}


# ============================================================
# Customers
# ============================================================

@mcp.tool()
def list_customers() -> list[dict]:
    """List all customers."""
    logger.info("Listing customers")
    client = _get_client()
    try:
        return client.list_customers()
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def get_customer(customer_id: str) -> dict:
    """Get customer details including communicationPreference."""
    logger.info("Getting customer %s", customer_id)
    client = _get_client()
    try:
        return client.get_customer(customer_id)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def create_customer(name: str, phone: str = None,
                    communication_preference: str = "whatsapp",
                    email: str = None, company: str = None) -> dict:
    """
    Create a new customer. REQUIRES name only. Phone is optional.

    Args:
        name: Customer name (required)
        phone: Phone number (optional — omit if not available)
        communication_preference: How to contact them — "whatsapp" or "phone" (default: whatsapp)
        email: Email address (optional)
        company: Company name (optional)

    Returns:
        Created customer with ID
    """
    logger.info("Creating customer: %s (contact: %s)", name, communication_preference)
    client = _get_client()
    try:
        return client.create_customer(name, phone, communication_preference,
                                      email, company)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def update_customer(customer_id: str, name: str = None, phone: str = None,
                    communication_preference: str = None, email: str = None,
                    company: str = None) -> dict:
    """
    Update a customer. Only provided fields are updated.

    Args:
        customer_id: Customer ID to update
        name: New name (optional)
        phone: New phone (optional)
        communication_preference: "whatsapp" or "phone" (optional)
        email: New email (optional)
        company: New company (optional)
    """
    logger.info("Updating customer %s", customer_id)
    client = _get_client()
    try:
        updates = {}
        if name: updates["name"] = name
        if phone: updates["phone"] = phone
        if communication_preference: updates["communicationPreference"] = communication_preference
        if email: updates["email"] = email
        if company: updates["company"] = company
        return client.update_customer(customer_id, **updates)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


# ============================================================
# Quotes
# ============================================================

@mcp.tool()
def list_quotes(status: str = None) -> list[dict]:
    """
    List quotes.

    Args:
        status: Filter by status (ACTIVE, APPROVED, CONVERTED, etc.)
    """
    logger.info("Listing quotes (status=%s)", status)
    client = _get_client()
    try:
        return client.list_quotes(status)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def get_quote(quote_id: str) -> dict:
    """Get quote details with items, pricing, and customer info."""
    logger.info("Getting quote %s", quote_id)
    client = _get_client()
    try:
        return client.get_quote(quote_id)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def create_quote(customer_id: str, items: list[dict],
                 materials: list[dict] = None, notes: str = None) -> dict:
    """
    Create a new quote. REQUIRES customer_id and at least one item.

    WORKFLOW: This is step 1. After creating, approve it before converting to order.

    Args:
        customer_id: Customer ID (get from list_customers)
        items: List of items, each with:
            - description: Item description (required)
            - quantity: Number of units (required)
            - unitPriceCents: Price per unit in cents (optional, default 0)
            - widthMm: Width in mm (optional)
            - heightMm: Height in mm (optional)
        materials: List of materials needed (optional)
        notes: Additional notes/observations (optional)

    Returns:
        Created quote with ID and status ACTIVE

    Next step: approve_quote(quote_id)
    """
    logger.info("Creating quote for customer %s", customer_id)
    client = _get_client()
    try:
        return client.create_quote(customer_id, items, materials, notes)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def approve_quote(quote_id: str) -> dict:
    """
    Approve a quote. REQUIRED before converting to order.

    WORKFLOW: This is step 2.

    Args:
        quote_id: Quote ID to approve

    Next step: convert_quote_to_order(quote_id)
    """
    logger.info("Approving quote %s", quote_id)
    client = _get_client()
    try:
        return client.approve_quote(quote_id)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def delete_quote(quote_id: str) -> dict:
    """Delete a quote. WARNING: Irreversible. Only ACTIVE quotes can be deleted."""
    logger.info("Deleting quote %s", quote_id)
    client = _get_client()
    try:
        return client.delete_quote(quote_id)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


# ============================================================
# Orders
# ============================================================

@mcp.tool()
def convert_quote_to_order(quote_id: str) -> dict:
    """
    Convert an approved quote to a production order.

    WORKFLOW ENFORCEMENT: Quote MUST be in APPROVED status.
    If not, tool returns error explaining what to do first.

    Args:
        quote_id: Quote ID to convert (must be approved first)

    ERROR if quote is not approved. Fix: approve_quote(quote_id) first.
    """
    logger.info("Converting quote %s to order", quote_id)
    client = _get_client()
    try:
        return client.convert_quote_to_order(quote_id)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def get_order(order_id: str) -> dict:
    """Get order details."""
    logger.info("Getting order %s", order_id)
    client = _get_client()
    try:
        return client.get_order(order_id)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


# ============================================================
# PDF Export
# ============================================================

@mcp.tool()
def export_quote_pdf(quote_id: str) -> str:
    """
    Export a quote as PDF.

    Args:
        quote_id: Quote ID to export

    Returns:
        Base64-encoded PDF content
    """
    logger.info("Exporting quote PDF: %s", quote_id)
    client = _get_client()
    try:
        content = client.get_quote_pdf(quote_id)
        import base64
        return base64.b64encode(content).decode()
    except Exception as e:
        return str(_handle_error(e))
    finally:
        client.close()


@mcp.tool()
def export_remision_pdf(order_id: str) -> str:
    """
    Export a remision (delivery note) PDF for an order.

    Args:
        order_id: Order ID

    Returns:
        Base64-encoded PDF content
    """
    logger.info("Exporting remision PDF: %s", order_id)
    client = _get_client()
    try:
        content = client.get_remision_pdf(order_id)
        import base64
        return base64.b64encode(content).decode()
    except Exception as e:
        return str(_handle_error(e))
    finally:
        client.close()


# ============================================================
# Payments
# ============================================================

@mcp.tool()
def list_payments(order_id: str) -> list[dict]:
    """List payments for an order."""
    logger.info("Listing payments for order %s", order_id)
    client = _get_client()
    try:
        return client.list_payments(order_id)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def register_payment(order_id: str, amount: float,
                     method: str = "cash", notes: str = None) -> dict:
    """
    Register a payment for an order.

    Args:
        order_id: Order ID to pay
        amount: Payment amount (must be positive)
        method: Payment method (cash, transfer, card)
        notes: Optional notes
    """
    logger.info("Registering payment: $%s for order %s", amount, order_id)
    client = _get_client()
    try:
        return client.register_payment(order_id, amount, method, notes)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


# ============================================================
# Materials
# ============================================================

@mcp.tool()
def list_materials() -> list[dict]:
    """List all inventory materials."""
    logger.info("Listing materials")
    client = _get_client()
    try:
        return client.list_materials()
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def create_material(name: str, thickness_mm: str = None,
                    sheet_width_mm: int = None,
                    sheet_height_mm: int = None) -> dict:
    """
    Create a new inventory material.

    Args:
        name: Material name
        thickness_mm: Thickness in mm (e.g., "3", "6", "9")
        sheet_width_mm: Sheet width in mm
        sheet_height_mm: Sheet height in mm
    """
    logger.info("Creating material: %s", name)
    client = _get_client()
    try:
        return client.create_material(name, thickness_mm,
                                      sheet_width_mm, sheet_height_mm)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


# ============================================================
# Catalog
# ============================================================

@mcp.tool()
def list_catalog_products() -> list[dict]:
    """List catalog products."""
    logger.info("Listing catalog products")
    client = _get_client()
    try:
        return client.list_catalog_products()
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


# ============================================================
# Costs
# ============================================================

@mcp.tool()
def get_rates() -> list[dict]:
    """Get current cutting/engraving rates."""
    logger.info("Getting rates")
    client = _get_client()
    try:
        return client.get_rates()
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def list_cutters() -> list[dict]:
    """List available cutters/tools."""
    logger.info("Listing cutters")
    client = _get_client()
    try:
        return client.list_cutters()
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


# ============================================================
# Users
# ============================================================

@mcp.tool()
def list_users() -> list[dict]:
    """List LaserBox users."""
    logger.info("Listing users")
    client = _get_client()
    try:
        return client.list_users()
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


# ============================================================
# System
# ============================================================

@mcp.tool()
def health_check() -> dict:
    """Check LaserBox server status."""
    logger.info("Health check")
    client = _get_client()
    try:
        return client.health_check()
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


# ============================================================
# Quote Updates
# ============================================================

@mcp.tool()
def update_quote(quote_id: str, customer_id: str = None, items: list[dict] = None,
                 materials: list[dict] = None, notes: str = None) -> dict:
    """
    Update an existing quote. Only provided fields are updated.

    Use this to set/update item prices (unitPriceCents) after creation.

    Args:
        quote_id: Quote ID to update
        customer_id: Customer ID (required by API — get from list_customers or get_quote)
        items: New items list (replaces all items). Each item:
            - description: Item description
            - quantity: Number of units
            - unitPriceCents: Price per unit in cents
            - widthMm: Width in mm (optional)
            - heightMm: Height in mm (optional)
        materials: New materials list (optional)
        notes: New observations (optional)

    Returns:
        Updated quote
    """
    logger.info("Updating quote %s", quote_id)
    client = _get_client()
    try:
        # Fetch current quote to get customerId if not provided
        if customer_id is None:
            current = client.get_quote(quote_id)
            customer_id = current.get("customerId")
        updates = {}
        if customer_id is not None: updates["customerId"] = customer_id
        if items is not None: updates["items"] = items
        if materials is not None: updates["materials"] = materials
        if notes is not None: updates["observations"] = notes
        return client.update_quote(quote_id, **updates)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


# ============================================================
# Prompts
# ============================================================

@mcp.prompt()
def guide_create_quote() -> str:
    """Step-by-step guide for creating a quote with correct workflow."""
    return """To create a quote, follow these steps:

1. LIST customers with list_customers() to find or confirm the customer
2. If customer doesn't exist, CREATE one with create_customer(name, phone?)
3. CREATE quote with create_quote(customer_id, items=[{
     "description": "Product description",
     "quantity": 1,
     "unitPriceCents": 15000,  ← price in cents (MXN)
     "widthMm": 300,            ← optional
     "heightMm": 200            ← optional
   }])
4. To update prices later: update_quote(quote_id, items=[{...}])
5. APPROVE with approve_quote(quote_id)
6. CONVERT to order with convert_quote_to_order(quote_id)

RULES:
- unitPriceCents is in CENTS (15000 = $150.00 MXN)
- Quote total is calculated automatically from items
- Only ACTIVE quotes can be edited or deleted
- Only APPROVED quotes can be converted to orders
- Phone is optional for customers (omit if not available)"""


@mcp.prompt()
def guide_list_prompts() -> str:
    """List all available prompts and their descriptions."""
    return """Available prompts:
- guide_create_quote: Step-by-step guide for creating a quote with correct workflow

Use get_prompt("guide_create_quote") for detailed instructions."""


if __name__ == "__main__":
    logger.info("Starting LaserBox MCP Server...")
    logger.info("Server: %s", LB_URL)
    logger.info("User: %s", LB_USER)
    mcp.run()
