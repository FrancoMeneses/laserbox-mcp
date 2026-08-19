# LaserBox MCP

Model Context Protocol server for [LaserBox](https://github.com/FrancoMeneses/laser-box-app) — CNC laser cutting business management.

## Features

- **Workflow Enforcement**: Quotes → Approve → Order → Payment (skipped steps are rejected)
- **Customer Management**: CRUD operations
- **Quote Management**: Create, approve, convert to production orders
- **Production Orders**: Track orders and generate delivery notes (PDF)
- **Payment Tracking**: Register and list payments per order
- **Inventory Management**: Materials, lots, suppliers, movements
- **Catalog Products**: Product catalog with pricing
- **Cost Management**: Cutting rates and cutter configuration

## Installation

```bash
git clone https://github.com/FrancoMeneses/laserbox-mcp.git
cd laserbox-mcp
pip install -r requirements.txt
```

## Configuration

```bash
export LB_URL="http://your-laserbox-host:4000"
export LB_USER="your-username@laserbox.local"
```

### With Hermes Agent

```yaml
mcp_servers:
  laserbox:
    command: "python3"
    args: ["/path/to/laserbox-mcp/src/laserbox/server.py"]
    env:
      LB_URL: "http://your-laserbox-host:4000"
      LB_USER: "agent@laserbox.local"
    timeout: 30
```

## Business Rules (Strictly Enforced)

```
1. customer → quote → approve → order → payment
2. Cannot create order without approved quote
3. Cannot register payment without order
4. Payment amount must be positive
5. Quote requires customer_id and at least one item
```

## Available Tools

### Customers
| Tool | Description |
|------|-------------|
| `list_customers` | List all customers |
| `get_customer` | Get customer details |
| `create_customer` | Create new customer |

### Quotes (Cotizaciones)
| Tool | Description |
|------|-------------|
| `list_quotes` | List quotes (filter by status) |
| `get_quote` | Get quote details |
| `create_quote` | Create quote with items |
| `approve_quote` | Approve quote (required before order) |
| `delete_quote` | Delete active quote |

### Orders
| Tool | Description |
|------|-------------|
| `convert_quote_to_order` | Convert approved quote to order |
| `get_order` | Get order details |
| `get_remision` | Get delivery note PDF |

### Payments
| Tool | Description |
|------|-------------|
| `list_payments` | List payments for order |
| `register_payment` | Register payment |

### Inventory
| Tool | Description |
|------|-------------|
| `list_inventory` | List materials |
| `create_material` | Create new material |
| `add_lot` | Add lot to material |
| `list_suppliers` | List suppliers |

### Catalog
| Tool | Description |
|------|-------------|
| `list_catalog_products` | List products |
| `create_catalog_product` | Create product |

### Costs
| Tool | Description |
|------|-------------|
| `get_rates` | Get cutting rates |
| `list_cutters` | List cutters |

### System
| Tool | Description |
|------|-------------|
| `list_users` | List LaserBox users |
| `health_check` | Server status |

## API Compatibility

Tested with LaserBox API running on Pi5 (port 4000). Uses Prisma + SQLite backend.

## License

MIT
