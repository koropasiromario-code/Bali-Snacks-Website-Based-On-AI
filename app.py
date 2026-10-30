import os
import re
import hmac
import sqlite3
import secrets
from datetime import datetime
from functools import wraps
from urllib.parse import quote

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    flash, jsonify, g, abort
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)

app = Flask(__name__, instance_path=INSTANCE_DIR)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", ""),
    DATABASE=os.environ.get("DATABASE_PATH", os.path.join(INSTANCE_DIR, "bali_snack.sqlite3")),
    ADMIN_USERNAME=os.environ.get("ADMIN_USERNAME", "admin"),
    ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", ""),
    WHATSAPP_NUMBER=re.sub(r"\D", "", os.environ.get("WHATSAPP_NUMBER", "")),
    CURRENCY="IDR",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)

DEFAULT_PRODUCTS = [
    (1, "Pie Susu Bali", "Kue", 35000, "Pie renyah dengan isian susu lembut. Cocok untuk oleh-oleh.", "🥧", 30, 1),
    (2, "Kacang Disco", "Camilan", 25000, "Kacang berbalut tepung berbumbu yang renyah dan gurih.", "🥜", 40, 1),
    (3, "Klepon Bali", "Kue Tradisional", 18000, "Kue tradisional berisi gula merah dengan taburan kelapa.", "🍡", 20, 1),
    (4, "Kue Laklak", "Kue Tradisional", 20000, "Kue mungil khas Bali yang nikmat dengan kelapa dan gula merah.", "🥞", 20, 1),
    (5, "Pia Kacang Hijau", "Kue", 30000, "Pia dengan kulit berlapis dan isian kacang hijau manis.", "🥮", 25, 1),
    (6, "Keripik Pisang", "Camilan", 22000, "Irisan pisang yang renyah untuk teman bersantai.", "🍌", 35, 1),
]

def db_conn():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA busy_timeout = 5000")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = db_conn()
        db.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price INTEGER NOT NULL CHECK(price >= 0),
            description TEXT NOT NULL DEFAULT '',
            emoji TEXT NOT NULL DEFAULT '🍪',
            stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_code TEXT NOT NULL UNIQUE,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            items_json TEXT NOT NULL,
            total INTEGER NOT NULL CHECK(total >= 0),
            status TEXT NOT NULL DEFAULT 'Menunggu konfirmasi',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)
        count = db.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
        if count == 0:
            db.executemany(
                "INSERT INTO products(id,name,category,price,description,emoji,stock,active) VALUES(?,?,?,?,?,?,?,?)",
                DEFAULT_PRODUCTS
            )
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('store_name','Bali Snack AI')")
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('store_tagline','Cita rasa Bali, dukung UMKM lokal')")
        db.commit()

def money(value):
    return "Rp" + format(int(value), ",").replace(",", ".")
app.jinja_env.filters["money"] = money

import json as _json
def from_json_filter(value):
    try:
        return _json.loads(value or "[]")
    except (ValueError, TypeError):
        return []
app.jinja_env.filters["from_json"] = from_json_filter

def csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]
app.jinja_env.globals["csrf_token"] = csrf_token

@app.before_request
def csrf_protect():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        expected = session.get("_csrf_token", "")
        supplied = request.form.get("_csrf_token", "") or request.headers.get("X-CSRF-Token", "")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            abort(400, description="Token keamanan tidak valid. Muat ulang halaman lalu coba lagi.")

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Silakan masuk sebagai admin terlebih dahulu.", "warning")
            return redirect(url_for("admin_login", next=request.path))
        return fn(*args, **kwargs)
    return wrapped

def get_setting(key, default=""):
    row = db_conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

@app.context_processor
def inject_globals():
    return {
        "store_name": get_setting("store_name", "Bali Snack AI"),
        "store_tagline": get_setting("store_tagline", "Cita rasa Bali, dukung UMKM lokal"),
        "whatsapp_ready": bool(app.config["WHATSAPP_NUMBER"]),
    }

@app.route("/")
def index():
    products = db_conn().execute(
        "SELECT * FROM products WHERE active=1 ORDER BY id"
    ).fetchall()
    return render_template("index.html", products=[dict(p) for p in products])

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip().lower()[:500]
    if not message:
        return jsonify({"reply": "Silakan tulis pertanyaan tentang jajanan khas Bali."})
    products = db_conn().execute("SELECT * FROM products WHERE active=1 ORDER BY price").fetchall()
    if not products:
        reply = "Katalog sedang diperbarui. Silakan hubungi penjual untuk informasi produk."
    elif any(w in message for w in ["murah", "hemat", "budget", "terjangkau"]):
        picks = products[:3]
        reply = "Pilihan yang lebih hemat: " + ", ".join(f'{p["name"]} ({money(p["price"])})' for p in picks) + ". Harga mengikuti katalog saat ini."
    elif any(w in message for w in ["oleh-oleh", "oleh oleh", "souvenir", "dibawa"]):
        names = [p["name"] for p in products if any(w in (p["name"]+" "+p["description"]).lower() for w in ["pie", "kacang", "pia", "keripik"])]
        reply = "Untuk oleh-oleh, pertimbangkan " + (", ".join(names[:4]) if names else ", ".join(p["name"] for p in products[:3])) + ". Pastikan masa simpan dan kemasan cocok untuk perjalanan."
    elif any(w in message for w in ["gurih", "asin", "renyah"]):
        picks = [p["name"] for p in products if p["category"] == "Camilan"]
        reply = "Untuk camilan gurih atau renyah, coba " + (", ".join(picks) if picks else ", ".join(p["name"] for p in products[:3])) + "."
    elif any(w in message for w in ["manis", "kue", "tradisional"]):
        picks = [p["name"] for p in products if "kue" in p["category"].lower()]
        reply = "Untuk jajanan manis atau tradisional, pertimbangkan " + (", ".join(picks[:5]) if picks else ", ".join(p["name"] for p in products[:3])) + "."
    elif any(w in message for w in ["promo", "caption", "iklan", "promosi"]):
        reply = "Contoh caption: “🌺 Cita rasa Bali hadir untuk menemani harimu! Coba jajanan khas pilihan dari UMKM lokal kami. Hubungi kami untuk info stok dan pemesanan. #JajananBali #UMKMLokal”. Pastikan detail produk dan harga benar sebelum dipublikasikan."
    elif any(w in message for w in ["harga", "berapa", "biaya"]):
        reply = "Harga produk tersedia di katalog. Harga termurah saat ini " + money(products[0]["price"]) + " untuk " + products[0]["name"] + "."
    elif any(w in message for w in ["halo", "hai", "hello", "selamat"]):
        reply = "Om Swastyastu! 🌺 Selamat datang. Saya bisa membantu memilih jajanan, mencari pilihan hemat, atau memberi ide promosi."
    else:
        reply = "Saya dapat membantu rekomendasi jajanan, pilihan hemat, oleh-oleh, atau ide promosi. Apa yang Anda cari?"
    return jsonify({"reply": reply})

@app.route("/api/promo", methods=["POST"])
def promo():
    data = request.get_json(silent=True) or {}
    product = re.sub(r"[<>]", "", str(data.get("product", "")).strip())[:100]
    tone = str(data.get("tone", "hangat"))
    if not product:
        return jsonify({"caption": "Masukkan nama produk terlebih dahulu."}), 400
    if tone == "ceria":
        caption = f"🎉 Ngemil makin seru dengan {product}! 🌴\\n\\nYuk, nikmati camilan pilihan dari UMKM lokal. Cocok untuk teman santai atau buah tangan. Hubungi kami untuk info stok dan pemesanan!\\n\\n#JajananBali #UMKMLokal #BanggaBuatanIndonesia"
    elif tone == "formal":
        caption = f"Kami memperkenalkan {product}, pilihan jajanan untuk menemani aktivitas dan buah tangan Anda.\\n\\nHubungi kami untuk informasi ketersediaan dan pemesanan.\\n\\n#JajananBali #UMKMLokal"
    else:
        caption = f"🌺 Cita rasa Bali hadir untuk menemani harimu!\\n\\nYuk, coba {product} dari UMKM lokal kami. Pas untuk teman santai maupun buah tangan. Hubungi kami untuk informasi stok dan pemesanan.\\n\\n#JajananBali #UMKMLokal #BanggaBuatanIndonesia"
    return jsonify({"caption": caption})

@app.route("/pesan", methods=["POST"])
def order():
    db = db_conn()
    name = request.form.get("customer_name", "").strip()[:100]
    phone = request.form.get("phone", "").strip()[:30]
    address = request.form.get("address", "").strip()[:500]
    notes = request.form.get("notes", "").strip()[:500]
    raw_items = request.form.get("items_json", "")
    if not name or not phone or not address:
        flash("Nama, nomor telepon, dan alamat/patokan pengiriman wajib diisi.", "danger")
        return redirect(url_for("index") + "#produk")
    if not re.fullmatch(r"[0-9+() .-]{7,30}", phone):
        flash("Format nomor telepon belum valid. Periksa kembali.", "danger")
        return redirect(url_for("index") + "#produk")
    import json
    try:
        items = json.loads(raw_items)
        if not isinstance(items, list) or not items or len(items) > 30:
            raise ValueError()
        normalized = {}
        for item in items:
            pid = int(item["id"])
            qty = int(item["qty"])
            if qty < 1 or qty > 100:
                raise ValueError()
            normalized[pid] = normalized.get(pid, 0) + qty
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        flash("Keranjang tidak valid. Silakan pilih produk kembali.", "danger")
        return redirect(url_for("index") + "#produk")
    try:
        db.execute("BEGIN IMMEDIATE")
        rows = {}
        total = 0
        order_items = []
        for pid, qty in normalized.items():
            p = db.execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
            if not p:
                raise ValueError("Salah satu produk tidak tersedia.")
            if p["stock"] < qty:
                raise ValueError(f'Stok {p["name"]} tidak cukup. Sisa stok: {p["stock"]}.')
            line = p["price"] * qty
            total += line
            order_items.append({"id": p["id"], "name": p["name"], "price": p["price"], "qty": qty, "subtotal": line})
            rows[pid] = qty
        code = "BS" + datetime.now().strftime("%y%m%d") + secrets.token_hex(3).upper()
        db.execute(
            "INSERT INTO orders(order_code,customer_name,phone,address,notes,items_json,total) VALUES(?,?,?,?,?,?,?)",
            (code, name, phone, address, notes, json.dumps(order_items, ensure_ascii=False), total)
        )
        for pid, qty in rows.items():
            db.execute("UPDATE products SET stock=stock-? WHERE id=?", (qty, pid))
        db.commit()
    except ValueError as e:
        db.rollback()
        flash(str(e), "danger")
        return redirect(url_for("index") + "#produk")
    except sqlite3.Error:
        db.rollback()
        app.logger.exception("Gagal menyimpan pesanan")
        flash("Pesanan belum tersimpan karena kendala database. Silakan coba lagi.", "danger")
        return redirect(url_for("index") + "#produk")

    lines = [f"Pesanan {code}", f"Nama: {name}", f"Telepon: {phone}", f"Alamat/patokan: {address}", "Item:"]
    lines.extend([f'- {x["name"]} x{x["qty"]}: {money(x["subtotal"])}' for x in order_items])
    lines.append(f"Total: {money(total)}")
    if notes:
        lines.append("Catatan: " + notes)
    wa_url = None
    if app.config["WHATSAPP_NUMBER"]:
        wa_url = "https://wa.me/" + app.config["WHATSAPP_NUMBER"] + "?text=" + quote("\\n".join(lines))
    return render_template("order_success.html", code=code, total=total, wa_url=wa_url)

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        configured_password = app.config["ADMIN_PASSWORD"]
        if not configured_password:
            flash("ADMIN_PASSWORD belum diatur. Baca README.md untuk konfigurasi awal.", "danger")
        elif hmac.compare_digest(username, app.config["ADMIN_USERNAME"]) and hmac.compare_digest(configured_password, password):
            session.clear()
            session["admin_logged_in"] = True
            session["_csrf_token"] = secrets.token_urlsafe(32)
            flash("Berhasil masuk.", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Username atau password salah.", "danger")
    return render_template("admin_login.html")

@app.route("/admin/logout", methods=["POST"])
@admin_required
def admin_logout():
    session.clear()
    flash("Anda telah keluar.", "success")
    return redirect(url_for("index"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    db = db_conn()
    products = db.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    orders = db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 100").fetchall()
    total_orders = db.execute("SELECT COUNT(*) n FROM orders").fetchone()["n"]
    revenue = db.execute("SELECT COALESCE(SUM(total),0) n FROM orders WHERE status!='Dibatalkan'").fetchone()["n"]
    return render_template("admin.html", products=products, orders=orders, total_orders=total_orders, revenue=revenue)

@app.route("/admin/products/save", methods=["POST"])
@admin_required
def admin_save_product():
    db = db_conn()
    try:
        pid = request.form.get("id", "").strip()
        name = request.form.get("name", "").strip()[:100]
        category = request.form.get("category", "").strip()[:60]
        description = request.form.get("description", "").strip()[:500]
        emoji = request.form.get("emoji", "🍪").strip()[:8]
        price = int(request.form.get("price", "0"))
        stock = int(request.form.get("stock", "0"))
        active = 1 if request.form.get("active") == "1" else 0
        if not name or not category or price < 0 or stock < 0 or price > 1000000000 or stock > 1000000:
            raise ValueError()
        if pid:
            db.execute("UPDATE products SET name=?,category=?,price=?,description=?,emoji=?,stock=?,active=? WHERE id=?",
                       (name, category, price, description, emoji, stock, active, int(pid)))
            flash("Produk berhasil diperbarui.", "success")
        else:
            db.execute("INSERT INTO products(name,category,price,description,emoji,stock,active) VALUES(?,?,?,?,?,?,?)",
                       (name, category, price, description, emoji, stock, active))
            flash("Produk berhasil ditambahkan.", "success")
        db.commit()
    except (ValueError, sqlite3.Error):
        db.rollback()
        flash("Data produk tidak valid atau gagal disimpan.", "danger")
    return redirect(url_for("admin_dashboard") + "#produk-admin")

@app.route("/admin/orders/status", methods=["POST"])
@admin_required
def admin_order_status():
    code = request.form.get("order_code", "")
    status = request.form.get("status", "")
    allowed = {"Menunggu konfirmasi", "Diproses", "Selesai", "Dibatalkan"}
    if status not in allowed:
        abort(400)
    db = db_conn()
    db.execute("UPDATE orders SET status=? WHERE order_code=?", (status, code))
    db.commit()
    flash("Status pesanan diperbarui.", "success")
    return redirect(url_for("admin_dashboard") + "#pesanan-admin")

@app.route("/health")
def health():
    try:
        db_conn().execute("SELECT 1")
        return jsonify({"status": "ok", "database": "connected"})
    except sqlite3.Error:
        return jsonify({"status": "error"}), 503

@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", code=400, message=getattr(error, "description", "Permintaan tidak valid.")), 400

@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="Halaman tidak ditemukan."), 404

@app.errorhandler(413)
def too_large(error):
    return render_template("error.html", code=413, message="Ukuran permintaan terlalu besar."), 413

if not app.config["SECRET_KEY"]:
    # Development fallback only. Set SECRET_KEY in environment for deployment.
    app.config["SECRET_KEY"] = "dev-only-" + secrets.token_hex(16)

init_db()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG", "0") == "1")
