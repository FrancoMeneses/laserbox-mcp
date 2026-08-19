"""
LaserBox API Client.

Handles all communication with the LaserBox REST API.
Includes workflow validation to enforce business rules.

API Base: http://100.120.238.37:4000
No auth required (local network). X-User header tracks who made the request.
"""

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class LaserBoxError(Exception):
    """Base exception for LaserBox API errors."""
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code


class ValidationError(LaserBoxError):
    """Raised when workflow validation fails."""
    pass


class NotFoundError(LaserBoxError):
    """Raised when a resource is not found."""
    pass


class LaserBoxClient:
    """
    Client for LaserBox REST API.

    Enforces business workflows:
    - Quotes must be created before orders
    - Orders require customer_id and items
    - Payments require a valid order_id
    """

    def __init__(self, base_url: str, user: str = "mcp@laserbox.local"):
        self.base_url = base_url.rstrip("/")
        self.user = user
        self._http = httpx.Client(timeout=30.0)

    def _request(
        self, method: str, path: str,
        params: dict = None, json_data: dict = None,
    ) -> httpx.Response:
        """Make an API request with X-User header."""
        headers = {"X-User": self.user}
        url = f"{self.base_url}{path}"

        try:
            response = self._http.request(
                method, url, params=params, json=json_data, headers=headers
            )

            if response.status_code == 404:
                raise NotFoundError(f"Not found: {path}")
            if response.status_code >= 400:
                try:
                    err = response.json()
                    msg = err.get("error", err.get("message", response.text[:200]))
                except Exception:
                    msg = response.text[:200]
                raise LaserBoxError(f"API error {response.status_code}: {msg}")

            return response

        except httpx.RequestError as e:
            raise LaserBoxError(f"Connection failed: {e}")

    # ============================================================
    # Customers
    # ============================================================

    def list_customers(self) -> list[dict]:
        resp = self._request("GET", "/api/customers").json(); return resp.get("items", resp) if isinstance(resp, dict) and "items" in resp else resp

    def get_customer(self, customer_id: int) -> dict:
        return self._request("GET", f"/api/customers/{customer_id}").json()

    def create_customer(self, name: str, email: str = None, phone: str = None,
                        company: str = None) -> dict:
        data = {"name": name}
        if email: data["email"] = email
        if phone: data["phone"] = phone
        if company: data["company"] = company
        return self._request("POST", "/api/customers", json_data=data).json()

    def update_customer(self, customer_id: int, **kwargs) -> dict:
        return self._request("PATCH", f"/api/customers/{customer_id}", json_data=kwargs).json()

    # ============================================================
    # Quotes (Cotizaciones)
    # ============================================================

    def list_quotes(self, status: str = None) -> list[dict]:
        params = {}
        if status: params["status"] = status
        resp = self._request("GET", "/api/quotes", params=params).json(); return resp.get("items", resp) if isinstance(resp, dict) and "items" in resp else resp

    def get_quote(self, quote_id: int) -> dict:
        return self._request("GET", f"/api/quotes/{quote_id}").json()

    def create_quote(self, customer_id: int, items: list[dict],
                     materials: list[dict] = None, notes: str = None) -> dict:
        """
        Create a quote.

        Items format: [{"description": "...", "quantity": N, "width": N, "height": N}]
        """
        if not items:
            raise ValidationError("Quote requires at least one item")
        data = {"customerId": customer_id, "items": items}
        if materials: data["materials"] = materials
        if notes: data["notes"] = notes
        return self._request("POST", "/api/quotes", json_data=data).json()

    def update_quote(self, quote_id: int, **kwargs) -> dict:
        return self._request("PATCH", f"/api/quotes/{quote_id}", json_data=kwargs).json()

    def approve_quote(self, quote_id: int) -> dict:
        """Approve a quote — changes status to APPROVED."""
        return self._request("PATCH", f"/api/quotes/{quote_id}/status",
                           json_data={"status": "APPROVED"}).json()

    def delete_quote(self, quote_id: int) -> dict:
        self._request("DELETE", f"/api/quotes/{quote_id}")
        return {"message": f"Quote {quote_id} deleted"}

    # ============================================================
    # Orders (Órdenes de producción)
    # ============================================================

    def convert_quote_to_order(self, quote_id: int) -> dict:
        """
        Convert an approved quote to a production order.

        WORKFLOW ENFORCEMENT: Quote must exist and be in APPROVED status.
        """
        # First check quote status
        quote = self.get_quote(quote_id)
        status = quote.get("status", "").upper()
        if status not in ("APPROVED", "ACTIVE"):
            raise ValidationError(
                f"Cannot convert quote {quote_id} to order: "
                f"status is '{status}'. Quote must be APPROVED first. "
                f"Use approve_quote({quote_id}) first."
            )
        return self._request("POST", f"/api/orders/{quote_id}/convert").json()

    def get_order(self, order_id: int) -> dict:
        return self._request("GET", f"/api/orders/{order_id}").json()

    def get_remision(self, order_id: int) -> bytes:
        """Get remision PDF for an order."""
        response = self._request("GET", f"/api/orders/{order_id}/remision")
        return response.content

    # ============================================================
    # Payments (Pagos)
    # ============================================================

    def list_payments(self, order_id: int) -> list[dict]:
        return self._request("GET", f"/api/orders/{order_id}/payments").json()

    def register_payment(self, order_id: int, amount: float,
                         method: str = "cash", notes: str = None) -> dict:
        """Register a payment for an order."""
        if amount <= 0:
            raise ValidationError("Payment amount must be positive")
        data = {"amount": amount, "method": method}
        if notes: data["notes"] = notes
        return self._request("POST", f"/api/orders/{order_id}/payments",
                           json_data=data).json()

    # ============================================================
    # Inventory (Inventario)
    # ============================================================

    def list_inventory(self) -> list[dict]:
        resp = self._request("GET", "/api/materials").json(); return resp.get("items", resp) if isinstance(resp, dict) and "items" in resp else resp

    def create_material(self, name: str, unit: str = "m2",
                        stock: float = 0) -> dict:
        return self._request("POST", "/api/materials",
                           json_data={"name": name, "unit": unit, "stock": stock}).json()

    def add_lot(self, material_id: int, quantity: float,
                supplier_id: int = None, cost: float = None) -> dict:
        data = {"quantity": quantity}
        if supplier_id: data["supplierId"] = supplier_id
        if cost: data["cost"] = cost
        return self._request("POST", f"/api/inventory/{material_id}/lots",
                           json_data=data).json()

    def register_movement(self, material_id: int, type: str, quantity: float,
                          notes: str = None) -> dict:
        """Register inventory movement (entry/exit)."""
        data = {"type": type, "quantity": quantity}
        if notes: data["notes"] = notes
        return self._request("POST", "/api/inventory/movements",
                           json_data=data).json()

    def list_suppliers(self) -> list[dict]:
        resp = self._request("GET", "/api/suppliers").json(); return resp.get("items", resp) if isinstance(resp, dict) and "items" in resp else resp

    # ============================================================
    # Catalog Products
    # ============================================================

    def list_catalog_products(self) -> list[dict]:
        resp = self._request("GET", "/api/catalog-products").json(); return resp.get("items", resp) if isinstance(resp, dict) and "items" in resp else resp

    def create_catalog_product(self, name: str, description: str = None,
                               price: float = None) -> dict:
        data = {"name": name}
        if description: data["description"] = description
        if price: data["price"] = price
        return self._request("POST", "/api/catalog-products",
                           json_data=data).json()

    # ============================================================
    # Costs
    # ============================================================

    def get_rates(self) -> dict:
        return self._request("GET", "/api/costs/rates").json()

    def list_cutters(self) -> list[dict]:
        return self._request("GET", "/api/costs/cutters").json()

    # ============================================================
    # Files
    # ============================================================

    def upload_file(self, order_id: int, file_path: str, content: bytes) -> dict:
        """Upload file attachment to an order."""
        files = {"file": (file_path, content)}
        return self._request("POST", f"/api/files/orders/{order_id}/attachments",
                           json_data=None).json()

    def get_order_files_zip(self, order_id: int) -> bytes:
        """Download all files for an order as ZIP."""
        response = self._request("GET", f"/api/files/orders/{order_id}/files/zip")
        return response.content

    # ============================================================
    # Users
    # ============================================================

    def list_users(self) -> list[dict]:
        resp = self._request("GET", "/api/users").json(); return resp.get("items", resp) if isinstance(resp, dict) and "items" in resp else resp

    # ============================================================
    # System
    # ============================================================

    def health_check(self) -> dict:
        try:
            response = self._http.get(f"{self.base_url}/api/auth/me")
            return {"status": "reachable", "url": self.base_url}
        except httpx.RequestError as e:
            return {"status": "unreachable", "error": str(e)}

    def close(self):
        self._http.close()
