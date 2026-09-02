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
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code


class ValidationError(LaserBoxError):
    pass


class NotFoundError(LaserBoxError):
    pass


class LaserBoxClient:
    """
    Client for LaserBox REST API.

    Enforces business workflows:
    - Quotes must be created before orders
    - Orders require approved quotes
    - Customer creation requires communicationPreference
    """

    def __init__(self, base_url: str, user: str = "mcp@laserbox.local"):
        self.base_url = base_url.rstrip("/")
        self.user = user
        self._http = httpx.Client(timeout=30.0)

    def _request(self, method: str, path: str, params: dict = None,
                 json_data: dict = None) -> httpx.Response:
        headers = {"X-User": self.user}
        url = f"{self.base_url}{path}"
        try:
            response = self._http.request(method, url, params=params,
                                          json=json_data, headers=headers)
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

    def _extract_items(self, data) -> list[dict]:
        """Extract items array from API response (handles {items:[...]} format)."""
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        if isinstance(data, list):
            return data
        return []

    # ============================================================
    # Customers
    # ============================================================

    def list_customers(self) -> list[dict]:
        resp = self._request("GET", "/api/customers").json()
        return self._extract_items(resp)

    def get_customer(self, customer_id: str) -> dict:
        return self._request("GET", f"/api/customers/{customer_id}").json()

    def create_customer(self, name: str, phone: str = None,
                        communication_preference: str = "whatsapp",
                        email: str = None, company: str = None) -> dict:
        """
        Create a new customer.

        communication_preference must be: "whatsapp" or "phone"
        Phone is optional — omit if not available.
        """
        if communication_preference not in ("whatsapp", "phone"):
            raise ValidationError(
                f"communicationPreference must be 'whatsapp' or 'phone', "
                f"got '{communication_preference}'"
            )
        data: dict = {
            "name": name,
            "communicationPreference": communication_preference,
        }
        if phone: data["phone"] = phone
        if email: data["email"] = email
        if company: data["company"] = company
        return self._request("POST", "/api/customers", json_data=data).json()

    def update_customer(self, customer_id: str, **kwargs) -> dict:
        return self._request("PATCH", f"/api/customers/{customer_id}",
                           json_data=kwargs).json()

    # ============================================================
    # Quotes
    # ============================================================

    def list_quotes(self, status: str = None) -> list[dict]:
        params = {}
        if status: params["status"] = status
        resp = self._request("GET", "/api/quotes", params=params).json()
        return self._extract_items(resp)

    def get_quote(self, quote_id: str) -> dict:
        data = self._request("GET", f"/api/quotes/{quote_id}").json()
        # API wraps single quote in {quote: {...}}
        if isinstance(data, dict) and "quote" in data:
            return data["quote"]
        return data

    def create_quote(self, customer_id: str, items: list[dict],
                     materials: list[dict] = None, notes: str = None) -> dict:
        if not items:
            raise ValidationError("Quote requires at least one item")
        data = {"customerId": customer_id, "items": items}
        if materials: data["materials"] = materials
        if notes: data["observations"] = notes
        return self._request("POST", "/api/quotes", json_data=data).json()

    def update_quote(self, quote_id: str, **kwargs) -> dict:
        data = self._request("PATCH", f"/api/quotes/{quote_id}",
                           json_data=kwargs).json()
        # API wraps single quote in {quote: {...}}
        if isinstance(data, dict) and "quote" in data:
            return data["quote"]
        return data

    def approve_quote(self, quote_id: str) -> dict:
        return self._request("PATCH", f"/api/quotes/{quote_id}/status",
                           json_data={"status": "APPROVED"}).json()

    def delete_quote(self, quote_id: str) -> dict:
        self._request("DELETE", f"/api/quotes/{quote_id}")
        return {"message": f"Quote {quote_id} deleted"}

    def get_quote_pdf(self, quote_id: str) -> bytes:
        """Download quote as PDF."""
        response = self._request("GET", f"/api/quotes/{quote_id}/pdf")
        return response.content

    # ============================================================
    # Orders
    # ============================================================

    def convert_quote_to_order(self, quote_id: str, responsible_user_id: str,
                                due_date: str, payment_amount_cents: int,
                                payment_method: str = 'cash',
                                payment_note: str | None = None) -> dict:
        quote = self.get_quote(quote_id)
        status = quote.get("status", "").upper()
        if status not in ("APPROVED", "ACTIVE"):
            raise ValidationError(
                f"Cannot convert quote {quote_id}: status is '{status}'. "
                f"Must be ACTIVE or APPROVED."
            )
        from datetime import datetime, timezone
        body = {
            "responsibleUserId": responsible_user_id,
            "dueDate": due_date,
            "materialReservationMode": "PENDING",
            "payment": {
                "amountCents": payment_amount_cents,
                "method": payment_method,
                "receivedAt": datetime.now(timezone.utc).isoformat()
            },
            "reservations": [],
            "fulfillmentPlan": []
        }
        if payment_note:
            body["payment"]["note"] = payment_note
        return self._request("POST", f"/api/quotes/{quote_id}/convert",
                             json_data=body).json()

    def get_order(self, order_id: str) -> dict:
        return self._request("GET", f"/api/orders/{order_id}").json()

    def get_remision_pdf(self, order_id: str) -> bytes:
        """Download remision (delivery note) PDF."""
        response = self._request("GET", f"/api/orders/{order_id}/remision")
        return response.content

    # ============================================================
    # Payments
    # ============================================================

    def list_payments(self, order_id: str) -> list[dict]:
        resp = self._request("GET", f"/api/orders/{order_id}/payments").json()
        return self._extract_items(resp)

    def register_payment(self, order_id: str, amount: float,
                         method: str = "cash", notes: str = None) -> dict:
        if amount <= 0:
            raise ValidationError("Payment amount must be positive")
        data = {"amount": amount, "method": method}
        if notes: data["notes"] = notes
        return self._request("POST", f"/api/orders/{order_id}/payments",
                           json_data=data).json()

    # ============================================================
    # Materials (Inventario)
    # ============================================================

    def list_materials(self) -> list[dict]:
        resp = self._request("GET", "/api/materials").json()
        return self._extract_items(resp)

    def create_material(self, name: str, thickness_mm: str = None,
                        sheet_width_mm: int = None,
                        sheet_height_mm: int = None) -> dict:
        data = {"name": name}
        if thickness_mm: data["thicknessMm"] = thickness_mm
        if sheet_width_mm: data["sheetWidthMm"] = sheet_width_mm
        if sheet_height_mm: data["sheetHeightMm"] = sheet_height_mm
        return self._request("POST", "/api/materials", json_data=data).json()

    # ============================================================
    # Catalog
    # ============================================================

    def list_catalog_products(self) -> list[dict]:
        resp = self._request("GET", "/api/catalog-products").json()
        return self._extract_items(resp)

    # ============================================================
    # Costs
    # ============================================================

    def get_rates(self) -> list[dict]:
        resp = self._request("GET", "/api/costs/rates").json()
        return self._extract_items(resp)

    def list_cutters(self) -> list[dict]:
        resp = self._request("GET", "/api/costs/cutters").json()
        return self._extract_items(resp)

    # ============================================================
    # Users
    # ============================================================

    def list_users(self) -> list[dict]:
        resp = self._request("GET", "/api/users").json()
        return self._extract_items(resp)

    # ============================================================
    # System
    # ============================================================

    def health_check(self) -> dict:
        try:
            self._http.get(f"{self.base_url}/api/auth/me")
            return {"status": "reachable", "url": self.base_url}
        except httpx.RequestError as e:
            return {"status": "unreachable", "error": str(e)}

    def close(self):
        self._http.close()
