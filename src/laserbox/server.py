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

# ============================================================
# Configuration
# ============================================================

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

# ============================================================
# MCP Server
# ============================================================

mcp = FastMCP(
    "LaserBox",
    instructions="""LaserBox CNC management tools with enforced workflows.

    BUSINESS RULES (strictly enforced):
    1. Quotes must be created BEFORE orders
    2. Quotes must be APPROVED before converting to orders
    3. Payments require a valid order_id
    4. Inventory movements must reference existing materials

    WORKFLOW: customer → quote → approve → order → payment
    Do NOT skip steps. The tools will reject invalid sequences.
    """
)


def _get_client() -> LaserBoxClient:
    return LaserBoxClient(url=LB_URL, user=LB_USER)


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
def get_customer(customer_id: int) -> dict:
    """Get customer details."""
    logger.info("Getting customer %s", customer_id)
    client = _get_client()
    try:
        return client.get_customer(customer_id)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def create_customer(name: str, email: str = None, phone: str = None,
                    company: str = None) -> dict:
    """
    Create a new customer.

    Args:
        name: Customer name (required)
        email: Email address (optional)
        phone: Phone number (optional)
        company: Company name (optional)
    """
    logger.info("Creating customer: %s", name)
    client = _get_client()
    try:
        return client.create_customer(name, email, phone, company)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


# ============================================================
# Quotes — WORKFLOW: create → approve → convert to order
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
def get_quote(quote_id: int) -> dict:
    """Get quote details with items and pricing."""
    logger.info("Getting quote %s", quote_id)
    client = _get_client()
    try:
        return client.get_quote(quote_id)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def create_quote(customer_id: int, items: list[dict],
                 materials: list[dict] = None, notes: str = None) -> dict:
    """
    Create a new quote. REQUIRES customer_id and items.

    WORKFLOW: This is step 1. After creating, you MUST approve it
    before converting to an order.

    Args:
        customer_id: Customer ID (get from list_customers)
        items: List of items, each with:
            - description: Item description
            - quantity: Number of units
            - width: Width in mm (optional)
            - height: Height in mm (optional)
        materials: List of materials needed (optional)
        notes: Additional notes (optional)

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
def approve_quote(quote_id: int) -> dict:
    """
    Approve a quote. REQUIRED before converting to order.

    WORKFLOW: This is step 2. Quote must be in ACTIVE/APPROVED status.

    Args:
        quote_id: Quote ID to approve

    Returns:
        Updated quote with status APPROVED

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
def delete_quote(quote_id: int) -> dict:
    """
    Delete a quote. WARNING: Irreversible.

    Only ACTIVE quotes can be deleted. APPROVED/CONVERTED quotes cannot.
    """
    logger.info("Deleting quote %s", quote_id)
    client = _get_client()
    try:
        return client.delete_quote(quote_id)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


# ============================================================
# Orders — WORKFLOW: quote → approve → convert → order
# ============================================================

@mcp.tool()
def convert_quote_to_order(quote_id: int) -> dict:
    """
    Convert an approved quote to a production order.

    WORKFLOW ENFORCEMENT:
    - Quote MUST exist
    - Quote MUST be in APPROVED status
    - If not, tool returns error explaining what to do first

    Args:
        quote_id: Quote ID to convert (must be approved first)

    Returns:
        Created order with ID

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
def get_order(order_id: int) -> dict:
    """Get order details."""
    logger.info("Getting order %s", order_id)
    client = _get_client()
    try:
        return client.get_order(order_id)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def get_remision(order_id: int) -> str:
    """
    Get remision (delivery note) PDF for an order.

    Returns base64-encoded PDF content.
    """
    logger.info("Getting remision for order %s", order_id)
    client = _get_client()
    try:
        content = client.get_remision(order_id)
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
def list_payments(order_id: int) -> list[dict]:
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
def register_payment(order_id: int, amount: float,
                     method: str = "cash", notes: str = None) -> dict:
    """
    Register a payment for an order.

    WORKFLOW: Order must exist before registering payment.

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
# Inventory
# ============================================================

@mcp.tool()
def list_inventory() -> list[dict]:
    """List all inventory materials."""
    logger.info("Listing inventory")
    client = _get_client()
    try:
        return client.list_inventory()
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def create_material(name: str, unit: str = "m2", stock: float = 0) -> dict:
    """
    Create a new inventory material.

    Args:
        name: Material name
        unit: Unit of measure (m2, kg, units, etc.)
        stock: Initial stock quantity
    """
    logger.info("Creating material: %s", name)
    client = _get_client()
    try:
        return client.create_material(name, unit, stock)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def add_lot(material_id: int, quantity: float,
            supplier_id: int = None, cost: float = None) -> dict:
    """
    Add a lot to an existing material.

    Args:
        material_id: Material ID
        quantity: Quantity to add
        supplier_id: Supplier ID (optional)
        cost: Cost per unit (optional)
    """
    logger.info("Adding lot: %s units to material %s", quantity, material_id)
    client = _get_client()
    try:
        return client.add_lot(material_id, quantity, supplier_id, cost)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


@mcp.tool()
def list_suppliers() -> list[dict]:
    """List all suppliers."""
    logger.info("Listing suppliers")
    client = _get_client()
    try:
        return client.list_suppliers()
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


@mcp.tool()
def create_catalog_product(name: str, description: str = None,
                           price: float = None) -> dict:
    """Create a catalog product."""
    logger.info("Creating catalog product: %s", name)
    client = _get_client()
    try:
        return client.create_catalog_product(name, description, price)
    except Exception as e:
        return _handle_error(e)
    finally:
        client.close()


# ============================================================
# Costs
# ============================================================

@mcp.tool()
def get_rates() -> dict:
    """Get current cutting rates."""
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
    """List available cutters."""
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
# Entry Point
# ============================================================

if __name__ == "__main__":
    logger.info("Starting LaserBox MCP Server...")
    logger.info("Server: %s", LB_URL)
    logger.info("User: %s", LB_USER)
    mcp.run()
