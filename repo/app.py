"""
Smart Inventory Management System - Flask Backend
DBMS Mini-Project
"""

from flask import Flask, render_template, request, jsonify, abort
import psycopg
from psycopg import Error
from psycopg.rows import dict_row
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
import os
from contextlib import contextmanager
from decimal import Decimal

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = Flask(__name__)

try:
    from flask_cors import CORS
    CORS(app)
except Exception:
    pass

# Database Configuration via environment (supports Render's DATABASE_URL)
DATABASE_URL = 'postgresql://root:H11IhJvyAz5eCVhLeyEduoFeeM0FiJG5@dpg-d415t62li9vc739f1j6g-a.oregon-postgres.render.com/inventory_azal'
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres'),
    'dbname': os.getenv('DB_NAME', 'postgres'),
}
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', 'dev')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin')

# Database Connection Helper
def get_db_connection():
    """Establish database connection"""
    try:
        if DATABASE_URL:
            connection = psycopg.connect(DATABASE_URL)
        else:
            connection = psycopg.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f"Error connecting to PostgreSQL: {e}")
        return None

def get_cursor(dictionary=False):
    """Get a safe cursor or abort if DB not connected"""
    conn = get_db_connection()
    if conn is None:
        abort(500, description="Database connection failed.")
    try:
        cursor = conn.cursor(row_factory=dict_row) if dictionary else conn.cursor()
        return conn, cursor
    except Error as e:
        print(f"Error creating cursor: {e}")
        abort(500, description="Database cursor creation failed.")


def _require_fields(data: Dict[str, Any], required_fields):
    missing = [f for f in required_fields if data.get(f) in (None, '')]
    if missing:
        abort(400, description=f"Missing required fields: {', '.join(missing)}")

def _require_non_negative_numbers(data: Dict[str, Any], numeric_fields):
    for field in numeric_fields:
        value = data.get(field)
        if value is None:
            continue
        try:
            if float(value) < 0:
                abort(400, description=f"{field} must be non-negative")
        except (TypeError, ValueError):
            abort(400, description=f"{field} must be a number")


def _run_sql_script(conn, script_text: str) -> int:
    """Execute a multi-statement SQL script. Returns number of statements run.

    Handles dollar-quoted blocks (e.g., $$ ... $$ or $tag$ ... $tag$) so we don't
    split function/procedure bodies on inner semicolons.
    """
    statements_run = 0
    with conn.cursor() as cur:
        buffer = ''
        in_dollar = False
        dollar_tag = None  # e.g., $$ or $func$

        for raw_line in script_text.splitlines():
            line = raw_line.rstrip('\n')
            stripped = line.strip()

            # Skip pure comment lines
            if not stripped or stripped.startswith('--'):
                # Preserve newlines inside buffer only if we're inside a dollar block
                if in_dollar:
                    buffer += line + '\n'
                continue

            # Detect start/end of dollar-quoted block
            if not in_dollar:
                # Find a $tag$ or $$ token
                idx = stripped.find('$$')
                tag_found = None
                if idx != -1:
                    tag_found = '$$'
                else:
                    # search for $tag$
                    start = stripped.find('$')
                    if start != -1:
                        end = stripped.find('$', start + 1)
                        if end != -1:
                            tag = stripped[start:end + 1]
                            # minimal sanity: require at least $x$
                            if len(tag) >= 3 and tag.startswith('$') and tag.endswith('$'):
                                tag_found = tag
                if tag_found:
                    in_dollar = True
                    dollar_tag = tag_found
            else:
                # inside dollar: check for closing tag
                if dollar_tag and (dollar_tag in stripped):
                    in_dollar = False
                    dollar_tag = None

            buffer += line + '\n'

            # Only terminate statement when not inside a dollar block and line ends with ';'
            if not in_dollar and stripped.endswith(';'):
                cur.execute(buffer)
                statements_run += 1
                buffer = ''

        if buffer.strip():
            cur.execute(buffer)
            statements_run += 1

    conn.commit()
    return statements_run


# ==================== AUTH HELPERS ====================

def _extract_bearer_token() -> Optional[str]:
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header.split(' ', 1)[1].strip()
    return None


@app.before_request
def _protect_api_routes():
    # Allow public endpoints
    path = request.path or ''
    if not path.startswith('/api'):
        return
    if path in ('/api/login', '/api/health') or path.startswith('/api/reports') and request.method == 'GET':
        return
    token = _extract_bearer_token()
    if token != ADMIN_TOKEN:
        return jsonify({'error': 'Unauthorized'}), 401


# ==================== ROUTES ====================

# Login as root route
@app.route('/')
def login_page():
    """Render login page"""
    return render_template('login.html')

# App dashboard
@app.route('/app')
def index():
    """Render main application"""
    return render_template('index.html')

# Health check
@app.route('/health', methods=['GET'])
def health():
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({'status': 'unhealthy', 'db': 'down'}), 500
        conn.close()
        return jsonify({'status': 'ok', 'db': 'up'}), 200
    except Exception:
        return jsonify({'status': 'unhealthy'}), 500

@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.get_json(silent=True) or {}
        username = str(data.get('username', '')).strip()
        password = str(data.get('password', ''))
        if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
            return jsonify({'error': 'Invalid credentials'}), 401
        return jsonify({'token': ADMIN_TOKEN, 'user': {'username': ADMIN_USERNAME}}), 200
    except Exception:
        return jsonify({'error': 'Login failed'}), 400

# Admin: Initialize PostgreSQL schema (use with caution). Protect with ADMIN_TOKEN.
@app.route('/admin/init-db', methods=['POST'])
def init_db():
    token = request.args.get('token') or request.headers.get('X-Admin-Token')
    if token != ADMIN_TOKEN:
        abort(403, description='Forbidden')
    conn = get_db_connection()
    if conn is None:
        abort(500, description='DB connection failed')
    try:
        schema_sql = """
DROP VIEW IF EXISTS lowstockproducts;
DROP VIEW IF EXISTS salessummary;

DROP TABLE IF EXISTS sales;
DROP TABLE IF EXISTS purchase;
DROP TABLE IF EXISTS product;
DROP TABLE IF EXISTS customer;
DROP TABLE IF EXISTS supplier;

CREATE TABLE supplier (
    supplierid SERIAL PRIMARY KEY,
    suppliername VARCHAR(100) NOT NULL,
    contactperson VARCHAR(100),
    phone VARCHAR(20),
    email VARCHAR(100),
    address TEXT,
    createdat TIMESTAMP DEFAULT now()
);

CREATE TABLE customer (
    customerid SERIAL PRIMARY KEY,
    customername VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(100),
    address TEXT,
    createdat TIMESTAMP DEFAULT now()
);

CREATE TABLE product (
    productid SERIAL PRIMARY KEY,
    productname VARCHAR(100) NOT NULL,
    description TEXT,
    category VARCHAR(50),
    price NUMERIC(10,2) NOT NULL,
    quantity INT DEFAULT 0,
    reorderlevel INT DEFAULT 10,
    supplierid INT REFERENCES supplier(supplierid) ON DELETE SET NULL,
    createdat TIMESTAMP DEFAULT now(),
    updatedat TIMESTAMP DEFAULT now()
);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updatedat = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_product_updated_at
BEFORE UPDATE ON product
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TABLE sales (
    saleid SERIAL PRIMARY KEY,
    productid INT NOT NULL REFERENCES product(productid) ON DELETE CASCADE,
    customerid INT NOT NULL REFERENCES customer(customerid) ON DELETE CASCADE,
    quantitysold INT NOT NULL,
    totalamount NUMERIC(10,2) NOT NULL,
    saledate TIMESTAMP DEFAULT now()
);

CREATE TABLE purchase (
    purchaseid SERIAL PRIMARY KEY,
    productid INT NOT NULL REFERENCES product(productid) ON DELETE CASCADE,
    supplierid INT NOT NULL REFERENCES supplier(supplierid) ON DELETE CASCADE,
    quantitypurchased INT NOT NULL,
    unitcost NUMERIC(10,2) NOT NULL,
    totalcost NUMERIC(10,2) NOT NULL,
    purchasedate TIMESTAMP DEFAULT now()
);

CREATE VIEW lowstockproducts AS
SELECT 
    p.productid AS "ProductID",
    p.productname AS "ProductName",
    p.category AS "Category",
    p.quantity AS "Quantity",
    p.reorderlevel AS "ReorderLevel",
    p.price AS "Price",
    (p.reorderlevel - p.quantity) AS "QuantityNeeded",
    s.suppliername AS "SupplierName"
FROM product p
LEFT JOIN supplier s ON p.supplierid = s.supplierid
WHERE p.quantity < p.reorderlevel
ORDER BY "QuantityNeeded" DESC;

CREATE VIEW salessummary AS
SELECT 
    s.saleid AS "SaleID",
    s.saledate AS "SaleDate",
    p.productname AS "ProductName",
    c.customername AS "CustomerName",
    s.quantitysold AS "QuantitySold",
    s.totalamount AS "TotalAmount",
    p.category AS "Category"
FROM sales s
JOIN product p ON s.productid = p.productid
JOIN customer c ON s.customerid = c.customerid
ORDER BY s.saledate DESC;

CREATE INDEX idx_product_category ON product(category);
CREATE INDEX idx_product_quantity ON product(quantity);
CREATE INDEX idx_sales_date ON sales(saledate);
CREATE INDEX idx_purchase_date ON purchase(purchasedate);
        """
        count = _run_sql_script(conn, schema_sql)
        return jsonify({'message': 'Schema initialized', 'statementsRun': count}), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# ==================== PRODUCT ROUTES ====================

@app.route('/api/products', methods=['GET'])
def get_products():
    """Get all products with supplier info"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        
        query = """
            SELECT 
                p.productid AS "ProductID",
                p.productname AS "ProductName",
                p.description AS "Description",
                p.category AS "Category",
                p.price AS "Price",
                p.quantity AS "Quantity",
                p.reorderlevel AS "ReorderLevel",
                p.supplierid AS "SupplierID",
                s.suppliername AS "SupplierName"
            FROM product p
            LEFT JOIN supplier s ON p.supplierid = s.supplierid
            ORDER BY p.productid DESC
        """
        cursor.execute(query)
        products = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify(products), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    """Get single product by ID"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        
        query = (
            "SELECT "
            "productid AS \"ProductID\", productname AS \"ProductName\", description AS \"Description\", "
            "category AS \"Category\", price AS \"Price\", quantity AS \"Quantity\", "
            "reorderlevel AS \"ReorderLevel\", supplierid AS \"SupplierID\" "
            "FROM product WHERE productid = %s"
        )
        cursor.execute(query, (product_id,))
        product = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if product:
            return jsonify(product), 200
        return jsonify({'error': 'Product not found'}), 404
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/products', methods=['POST'])
def add_product():
    """Add new product"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'Invalid JSON data'}), 400
        _require_fields(data, ['ProductName', 'Price'])
        _require_non_negative_numbers(data, ['Price', 'Quantity', 'ReorderLevel'])
            
        conn, cursor = get_cursor(dictionary=True)
        
        query = """
            INSERT INTO Product (ProductName, Description, Category, Price, 
                                Quantity, ReorderLevel, SupplierID)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING ProductID
        """
        values = (
            data.get('ProductName'),
            data.get('Description', ''),
            data.get('Category', ''),
            data.get('Price'),
            data.get('Quantity', 0),
            data.get('ReorderLevel', 10),
            data.get('SupplierID')
        )
        
        cursor.execute(query, values)
        row = cursor.fetchone()
        product_id = row['productid'] if isinstance(row, dict) else row[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Product added successfully', 'ProductID': product_id}), 201
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    """Update existing product"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'Invalid JSON data'}), 400
        _require_fields(data, ['ProductName', 'Price'])
        _require_non_negative_numbers(data, ['Price', 'Quantity', 'ReorderLevel'])
            
        conn, cursor = get_cursor(dictionary=True)
        
        query = """
            UPDATE Product 
            SET ProductName=%s, Description=%s, Category=%s, Price=%s,
                Quantity=%s, ReorderLevel=%s, SupplierID=%s
            WHERE ProductID=%s
        """
        values = (
            data.get('ProductName'),
            data.get('Description', ''),
            data.get('Category', ''),
            data.get('Price'),
            data.get('Quantity'),
            data.get('ReorderLevel'),
            data.get('SupplierID'),
            product_id
        )
        
        cursor.execute(query, values)
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Product updated successfully'}), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    """Delete product"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        
        query = "DELETE FROM Product WHERE ProductID = %s"
        cursor.execute(query, (product_id,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Product deleted successfully'}), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

# ==================== SUPPLIER ROUTES ====================

@app.route('/api/suppliers', methods=['GET'])
def get_suppliers():
    """Get all suppliers"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        
        query = (
            "SELECT supplierid AS \"SupplierID\", suppliername AS \"SupplierName\", "
            "contactperson AS \"ContactPerson\", phone AS \"Phone\", email AS \"Email\", address AS \"Address\" "
            "FROM supplier ORDER BY supplierid DESC"
        )
        cursor.execute(query)
        suppliers = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify(suppliers), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/suppliers', methods=['POST'])
def add_supplier():
    """Add new supplier"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'Invalid JSON data'}), 400
        _require_fields(data, ['SupplierName'])
            
        conn, cursor = get_cursor(dictionary=True)
        
        query = """
            INSERT INTO Supplier (SupplierName, ContactPerson, Phone, Email, Address)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING SupplierID
        """
        values = (
            data.get('SupplierName'),
            data.get('ContactPerson', ''),
            data.get('Phone', ''),
            data.get('Email', ''),
            data.get('Address', '')
        )
        
        cursor.execute(query, values)
        row = cursor.fetchone()
        supplier_id = row['supplierid'] if isinstance(row, dict) else row[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Supplier added successfully', 'SupplierID': supplier_id}), 201
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/suppliers/<int:supplier_id>', methods=['GET'])
def get_supplier(supplier_id):
    """Get single supplier by ID"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        query = (
            "SELECT supplierid AS \"SupplierID\", suppliername AS \"SupplierName\", "
            "contactperson AS \"ContactPerson\", phone AS \"Phone\", email AS \"Email\", address AS \"Address\" "
            "FROM supplier WHERE supplierid = %s"
        )
        cursor.execute(query, (supplier_id,))
        supplier = cursor.fetchone()
        cursor.close()
        conn.close()
        if supplier:
            return jsonify(supplier), 200
        return jsonify({'error': 'Supplier not found'}), 404
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
def update_supplier(supplier_id):
    """Update supplier"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'Invalid JSON data'}), 400
        _require_fields(data, ['SupplierName'])
            
        conn, cursor = get_cursor(dictionary=True)
        
        query = """
            UPDATE Supplier 
            SET SupplierName=%s, ContactPerson=%s, Phone=%s, Email=%s, Address=%s
            WHERE SupplierID=%s
        """
        values = (
            data.get('SupplierName'),
            data.get('ContactPerson', ''),
            data.get('Phone', ''),
            data.get('Email', ''),
            data.get('Address', ''),
            supplier_id
        )
        
        cursor.execute(query, values)
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Supplier updated successfully'}), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/suppliers/<int:supplier_id>', methods=['DELETE'])
def delete_supplier(supplier_id):
    """Delete supplier"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        
        query = "DELETE FROM Supplier WHERE SupplierID = %s"
        cursor.execute(query, (supplier_id,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Supplier deleted successfully'}), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

# ==================== CUSTOMER ROUTES ====================

@app.route('/api/customers', methods=['GET'])
def get_customers():
    """Get all customers"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        
        query = (
            "SELECT customerid AS \"CustomerID\", customername AS \"CustomerName\", "
            "phone AS \"Phone\", email AS \"Email\", address AS \"Address\" "
            "FROM customer ORDER BY customerid DESC"
        )
        cursor.execute(query)
        customers = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify(customers), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/customers', methods=['POST'])
def add_customer():
    """Add new customer"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'Invalid JSON data'}), 400
        _require_fields(data, ['CustomerName'])
            
        conn, cursor = get_cursor(dictionary=True)
        
        query = """
            INSERT INTO Customer (CustomerName, Phone, Email, Address)
            VALUES (%s, %s, %s, %s)
            RETURNING CustomerID
        """
        values = (
            data.get('CustomerName'),
            data.get('Phone', ''),
            data.get('Email', ''),
            data.get('Address', '')
        )
        
        cursor.execute(query, values)
        row = cursor.fetchone()
        customer_id = row['customerid'] if isinstance(row, dict) else row[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Customer added successfully', 'CustomerID': customer_id}), 201
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/customers/<int:customer_id>', methods=['GET'])
def get_customer_by_id(customer_id):
    """Get single customer by ID"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        query = (
            "SELECT customerid AS \"CustomerID\", customername AS \"CustomerName\", "
            "phone AS \"Phone\", email AS \"Email\", address AS \"Address\" "
            "FROM customer WHERE customerid = %s"
        )
        cursor.execute(query, (customer_id,))
        customer = cursor.fetchone()
        cursor.close()
        conn.close()
        if customer:
            return jsonify(customer), 200
        return jsonify({'error': 'Customer not found'}), 404
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/customers/<int:customer_id>', methods=['PUT'])
def update_customer(customer_id):
    """Update customer"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'Invalid JSON data'}), 400
        _require_fields(data, ['CustomerName'])
            
        conn, cursor = get_cursor(dictionary=True)
        
        query = """
            UPDATE Customer 
            SET CustomerName=%s, Phone=%s, Email=%s, Address=%s
            WHERE CustomerID=%s
        """
        values = (
            data.get('CustomerName'),
            data.get('Phone', ''),
            data.get('Email', ''),
            data.get('Address', ''),
            customer_id
        )
        
        cursor.execute(query, values)
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Customer updated successfully'}), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/customers/<int:customer_id>', methods=['DELETE'])
def delete_customer(customer_id):
    """Delete customer"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        
        query = "DELETE FROM Customer WHERE CustomerID = %s"
        cursor.execute(query, (customer_id,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Customer deleted successfully'}), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

# ==================== SALES ROUTES ====================

@app.route('/api/sales', methods=['GET'])
def get_sales():
    """Get all sales with details"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        
        query = """
            SELECT 
                s.saleid AS "SaleID",
                s.saledate AS "SaleDate",
                p.productname AS "ProductName",
                c.customername AS "CustomerName",
                s.quantitysold AS "QuantitySold",
                s.totalamount AS "TotalAmount"
            FROM sales s
            JOIN product p ON s.productid = p.productid
            JOIN customer c ON s.customerid = c.customerid
            ORDER BY s.saledate DESC
        """
        cursor.execute(query)
        sales = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify(sales), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sales', methods=['POST'])
def add_sale():
    """Add new sale and update product quantity"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'Invalid JSON data'}), 400
        _require_fields(data, ['ProductID', 'CustomerID', 'QuantitySold'])
        _require_non_negative_numbers(data, ['QuantitySold'])

        conn, cursor = get_cursor(dictionary=True)
        try:
            with conn.transaction():
                # Lock product row for update
                cursor.execute("SELECT Quantity, Price FROM Product WHERE ProductID = %s FOR UPDATE", 
                              (data.get('ProductID'),))
                product = cursor.fetchone()
                if not product:
                    return jsonify({'error': 'Product not found'}), 404

                quantity = product.get('quantity', 0) if isinstance(product, dict) else product[0]
                price = product.get('price', 0) if isinstance(product, dict) else product[1]
                quantity_sold = int(data.get('QuantitySold', 0))
                if quantity_sold <= 0:
                    return jsonify({'error': 'QuantitySold must be greater than 0'}), 400

                if quantity < quantity_sold:
                    return jsonify({'error': 'Insufficient stock'}), 400

                total_amount = float(price) * quantity_sold

                # Insert sale record
                query = """
                    INSERT INTO Sales (ProductID, CustomerID, QuantitySold, TotalAmount)
                    VALUES (%s, %s, %s, %s)
                    RETURNING SaleID
                """
                cursor.execute(query, (data.get('ProductID'), data.get('CustomerID'), 
                                      quantity_sold, total_amount))
                row = cursor.fetchone()
                sale_id = row['saleid'] if isinstance(row, dict) else row[0]

                # Update product quantity
                update_query = "UPDATE Product SET Quantity = Quantity - %s WHERE ProductID = %s"
                cursor.execute(update_query, (quantity_sold, data.get('ProductID')))

            return jsonify({'message': 'Sale recorded successfully', 'SaleID': sale_id}), 201
        finally:
            cursor.close()
            conn.close()
    except Error as e:
        return jsonify({'error': str(e)}), 500

# ==================== PURCHASE ROUTES ====================

@app.route('/api/purchases', methods=['GET'])
def get_purchases():
    """Get all purchases with details"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        
        query = """
            SELECT 
                pu.purchaseid AS "PurchaseID",
                pu.purchasedate AS "PurchaseDate",
                p.productname AS "ProductName",
                s.suppliername AS "SupplierName",
                pu.quantitypurchased AS "QuantityPurchased",
                pu.unitcost AS "UnitCost",
                pu.totalcost AS "TotalCost"
            FROM purchase pu
            JOIN product p ON pu.productid = p.productid
            JOIN supplier s ON pu.supplierid = s.supplierid
            ORDER BY pu.purchasedate DESC
        """
        cursor.execute(query)
        purchases = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify(purchases), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/purchases', methods=['POST'])
def add_purchase():
    """Add new purchase and update product quantity"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'Invalid JSON data'}), 400
        _require_fields(data, ['ProductID', 'SupplierID', 'QuantityPurchased', 'UnitCost'])
        _require_non_negative_numbers(data, ['QuantityPurchased', 'UnitCost'])

        conn, cursor = get_cursor(dictionary=True)
        try:
            with conn.transaction():
                unit_cost = float(data.get('UnitCost', 0))
                quantity_purchased = int(data.get('QuantityPurchased', 0))
                if quantity_purchased <= 0 or unit_cost < 0:
                    return jsonify({'error': 'QuantityPurchased must be > 0 and UnitCost >= 0'}), 400
                total_cost = unit_cost * quantity_purchased

                # Insert purchase record
                query = """
                    INSERT INTO Purchase (ProductID, SupplierID, QuantityPurchased, UnitCost, TotalCost)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING PurchaseID
                """
                cursor.execute(query, (data.get('ProductID'), data.get('SupplierID'), 
                                      quantity_purchased, unit_cost, total_cost))
                row = cursor.fetchone()
                purchase_id = row['purchaseid'] if isinstance(row, dict) else row[0]

                # Update product quantity
                update_query = "UPDATE Product SET Quantity = Quantity + %s WHERE ProductID = %s"
                cursor.execute(update_query, (quantity_purchased, data.get('ProductID')))

            return jsonify({'message': 'Purchase recorded successfully', 'PurchaseID': purchase_id}), 201
        finally:
            cursor.close()
            conn.close()
    except Error as e:
        return jsonify({'error': str(e)}), 500

# ==================== DASHBOARD & REPORTS ====================

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    """Get dashboard statistics"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        
        # Total products
        cursor.execute("SELECT COUNT(*) as total FROM Product")
        result = cursor.fetchone()
        total_products = 0
        if result and isinstance(result, dict) and 'total' in result:
            val = result['total']
            total_products = int(val) if isinstance(val, (int, float, str)) else 0
        
        # Total sales amount
        cursor.execute("SELECT COALESCE(SUM(TotalAmount), 0) AS total FROM Sales")
        result = cursor.fetchone()

        total_sales = 0.0
        if result and isinstance(result, dict) and 'total' in result:
            val = result['total']
            # Handle Decimal or numeric types safely
            if isinstance(val, Decimal):
                total_sales = float(val)
            elif isinstance(val, (int, float, str)):
                try:
                    total_sales = float(val)
                except ValueError:
                    total_sales = 0.0
            else:
                total_sales = 0.0
        
        # Low stock count
        cursor.execute("SELECT COUNT(*) as total FROM Product WHERE Quantity < ReorderLevel")
        result = cursor.fetchone()
        low_stock_count = 0
        if result and isinstance(result, dict) and 'total' in result:
            val = result['total']
            low_stock_count = int(val) if isinstance(val, (int, float, str)) else 0
        
        # Total customers
        cursor.execute("SELECT COUNT(*) as total FROM Customer")
        result = cursor.fetchone()
        total_customers = 0
        if result and isinstance(result, dict) and 'total' in result:
            val = result['total']
            total_customers = int(val) if isinstance(val, (int, float, str)) else 0
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'TotalProducts': total_products,
            'TotalSales': total_sales,
            'LowStockCount': low_stock_count,
            'TotalCustomers': total_customers
        }), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/low-stock', methods=['GET'])
def get_low_stock():
    """Get low stock products with supplier name"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        query = """
            SELECT 
                p.productid AS "ProductID",
                p.productname AS "ProductName",
                p.category AS "Category",
                p.quantity AS "Quantity",
                p.reorderlevel AS "ReorderLevel",
                p.price AS "Price",
                (p.reorderlevel - p.quantity) AS "QuantityNeeded",
                s.suppliername AS "SupplierName"
            FROM product p
            LEFT JOIN supplier s ON p.supplierid = s.supplierid
            WHERE p.quantity < p.reorderlevel
            ORDER BY "QuantityNeeded" DESC
        """
        cursor.execute(query)
        products = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(products), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/sales-summary', methods=['GET'])
def get_sales_summary():
    """Get sales summary"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        
        # Try view first, fallback to direct query
        try:
            query = "SELECT * FROM SalesSummary LIMIT 50"
            cursor.execute(query)
            sales = cursor.fetchall()
        except Error:
            # Fallback query if view doesn't exist
            query = """
                SELECT 
                    s.SaleID,
                    s.SaleDate,
                    p.ProductName,
                    c.CustomerName,
                    s.QuantitySold,
                    s.TotalAmount,
                    p.Category
                FROM Sales s
                JOIN Product p ON s.ProductID = p.ProductID
                JOIN Customer c ON s.CustomerID = c.CustomerID
                ORDER BY s.SaleDate DESC
                LIMIT 50
            """
            cursor.execute(query)
            sales = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify(sales), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/top-products', methods=['GET'])
def get_top_products():
    """Get top selling products"""
    try:
        conn, cursor = get_cursor(dictionary=True)
        
        query = """
            SELECT p.ProductName, SUM(s.QuantitySold) as TotalSold, 
                   SUM(s.TotalAmount) as Revenue
            FROM Sales s
            JOIN Product p ON s.ProductID = p.ProductID
            GROUP BY p.ProductID, p.ProductName
            ORDER BY TotalSold DESC
            LIMIT 10
        """
        cursor.execute(query)
        products = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify(products), 200
    except Error as e:
        return jsonify({'error': str(e)}), 500

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(400)
def bad_request(error):
    description = getattr(error, 'description', 'Bad request')
    return jsonify({'error': description}), 400

@app.errorhandler(500)
def internal_error(error):
    # In production, avoid leaking details; here we keep it generic
    return jsonify({'error': 'Internal server error'}), 500

@app.after_request
def apply_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    # Keep CSP relaxed due to external CDNs and inline scripts in template; tighten if you self-host assets
    response.headers['Content-Security-Policy'] = (
        "default-src 'self' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://cdnjs.cloudflare.com https://images.unsplash.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com https://cdn.jsdelivr.net"
    )
    return response

# ==================== RUN APPLICATION ====================

if __name__ == '__main__':
    app.run(debug=True, port=5000)