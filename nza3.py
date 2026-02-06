import streamlit as st
import streamlit.components.v1 as components
import json
import html
import base64
from datetime import datetime
import uuid
import qrcode
from io import BytesIO

# Firebase imports
import warnings
warnings.filterwarnings("ignore", message=".*Prefer using the 'filter' keyword argument instead.*", module="google.cloud.firestore")
import firebase_admin
from firebase_admin import credentials, firestore

# Auto-refresh
from streamlit_autorefresh import st_autorefresh

# Page config - nza2.py လို sidebar အမြဲပွဲထား
st.set_page_config(
    page_title="QR Code Menu System",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# nza2.py လို - header/footer/sidebar မဖျောက်ပါ။ Sidebar အမြဲပေါ်အောင် CSS မထည့်ပါ။

# ============================================
# FIREBASE CONNECTION
# ============================================
@st.cache_resource
def get_firebase_connection():
    """Firebase Firestore connection"""
    import os
    
    try:
        # Check if already initialized
        if not firebase_admin._apps:
            initialized = False
            
            # Try Streamlit secrets first (for cloud deployment)
            try:
                if 'firebase' in st.secrets:
                    creds_dict = dict(st.secrets["firebase"])
                    cred = credentials.Certificate(creds_dict)
                    firebase_admin.initialize_app(cred)
                    initialized = True
            except:
                pass  # No secrets, try local file
            
            # Use local credentials file
            if not initialized:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                creds_path = os.path.join(script_dir, "firebase_credentials.json")
                
                if not os.path.exists(creds_path):
                    st.error(f"❌ firebase_credentials.json မတွေ့ပါ: {creds_path}")
                    return None
                
                cred = credentials.Certificate(creds_path)
                firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        return db
    except Exception as e:
        st.error(f"❌ Firebase connection error: {e}")
        return None

# ============================================
# DATA FUNCTIONS - Much faster with Firebase!
# ============================================
@st.cache_data(ttl=30)
def load_stores(_db_id):
    """Load all stores"""
    db = firestore.client()
    stores = []
    docs = db.collection('stores').stream()
    for doc in docs:
        data = doc.to_dict()
        data['store_id'] = doc.id
        stores.append(data)
    return stores

@st.cache_data(ttl=30)
def load_categories(_db_id, store_id):
    """Load categories for a store"""
    db = firestore.client()
    categories = []
    docs = db.collection('stores').document(store_id).collection('categories').stream()
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        categories.append(data)
    return categories

@st.cache_data(ttl=30)
def load_menu_items(_db_id, store_id):
    """Load menu items for a store"""
    db = firestore.client()
    items = []
    docs = db.collection('stores').document(store_id).collection('menu_items').stream()
    for doc in docs:
        data = doc.to_dict()
        data['item_id'] = doc.id
        items.append(data)
    return items

@st.cache_data(ttl=5)  # Very short cache for real-time orders
def load_orders(_db_id, store_id):
    """Load orders for a store"""
    db = firestore.client()
    orders = []
    docs = db.collection('stores').document(store_id).collection('orders').order_by('timestamp', direction=firestore.Query.DESCENDING).stream()
    for doc in docs:
        data = doc.to_dict()
        data['order_id'] = doc.id
        orders.append(data)
    return orders

def clear_all_cache():
    load_stores.clear()
    load_categories.clear()
    load_menu_items.clear()
    load_orders.clear()

# ============================================
# STORE FUNCTIONS
# ============================================
def save_store(db, store_data):
    """Save new store"""
    store_id = store_data['store_id']
    db.collection('stores').document(store_id).set({
        'store_name': store_data['store_name'],
        'admin_key': store_data['admin_key'],
        'logo': store_data.get('logo', '☕'),
        'subtitle': store_data.get('subtitle', 'Food & Drinks'),
        'bg_color': store_data.get('bg_color', ''),
        'bg_image': store_data.get('bg_image', ''),
        'bg_counter': store_data.get('bg_counter', False),
        'created_at': firestore.SERVER_TIMESTAMP
    })
    clear_all_cache()

def update_store(db, store_id, new_data):
    """Update store"""
    db.collection('stores').document(store_id).update({
        'store_name': new_data['store_name'],
        'admin_key': new_data['admin_key'],
        'logo': new_data.get('logo', '☕'),
        'subtitle': new_data.get('subtitle', 'Food & Drinks'),
        'bg_color': new_data.get('bg_color', ''),
        'bg_image': new_data.get('bg_image', ''),
        'bg_counter': new_data.get('bg_counter', False)
    })
    clear_all_cache()

def delete_store(db, store_id):
    """Delete store and all subcollections"""
    store_ref = db.collection('stores').document(store_id)
    
    # Delete subcollections
    for subcoll in ['categories', 'menu_items', 'orders']:
        docs = store_ref.collection(subcoll).stream()
        for doc in docs:
            doc.reference.delete()
    
    # Delete store document
    store_ref.delete()
    clear_all_cache()

# ============================================
# CATEGORY FUNCTIONS
# ============================================
def save_category(db, store_id, category_name):
    """Save new category"""
    db.collection('stores').document(store_id).collection('categories').add({
        'category_name': category_name,
        'created_at': firestore.SERVER_TIMESTAMP
    })
    load_categories.clear()

def delete_category(db, store_id, category_id):
    """Delete category"""
    db.collection('stores').document(store_id).collection('categories').document(category_id).delete()
    load_categories.clear()

# ============================================
# MENU ITEM FUNCTIONS
# ============================================
def save_menu_item(db, store_id, item_data):
    """Save new menu item"""
    item_id = str(uuid.uuid4())[:8]
    db.collection('stores').document(store_id).collection('menu_items').document(item_id).set({
        'name': item_data['name'],
        'price': item_data['price'],
        'category': item_data['category'],
        'created_at': firestore.SERVER_TIMESTAMP
    })
    load_menu_items.clear()

def update_menu_item(db, store_id, item_id, new_data):
    """Update menu item"""
    db.collection('stores').document(store_id).collection('menu_items').document(item_id).update({
        'name': new_data['name'],
        'price': new_data['price'],
        'category': new_data['category']
    })
    load_menu_items.clear()

def delete_menu_item(db, store_id, item_id):
    """Delete menu item"""
    db.collection('stores').document(store_id).collection('menu_items').document(item_id).delete()
    load_menu_items.clear()

# ============================================
# ORDER FUNCTIONS
# ============================================
def save_order(db, store_id, order_data):
    """Save new order - Very fast with Firebase!"""
    order_id = str(uuid.uuid4())[:8]
    db.collection('stores').document(store_id).collection('orders').document(order_id).set({
        'table_no': order_data['table_no'],
        'items': order_data['items'],
        'total': order_data['total'],
        'status': 'pending',
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    load_orders.clear()
    return order_id

def update_order_status(db, store_id, order_id, new_status):
    """Update order status"""
    db.collection('stores').document(store_id).collection('orders').document(order_id).update({
        'status': new_status
    })
    load_orders.clear()

def get_order_status(db, store_id, order_id):
    """Get single order status for customer tracking (no cache - real-time)"""
    doc = db.collection('stores').document(store_id).collection('orders').document(order_id).get()
    if doc.exists:
        return doc.to_dict().get('status')
    return None

def delete_order(db, store_id, order_id):
    """Delete completed order"""
    db.collection('stores').document(store_id).collection('orders').document(order_id).delete()
    load_orders.clear()

def add_to_daily_sales(db, store_id, amount):
    """Add amount to daily sales total"""
    today = datetime.now().strftime("%Y-%m-%d")
    doc_ref = db.collection('stores').document(store_id).collection('daily_sales').document(today)
    
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        current_total = data.get('total', 0)
        current_count = data.get('order_count', 0)
        doc_ref.update({
            'total': current_total + amount,
            'order_count': current_count + 1
        })
    else:
        doc_ref.set({
            'total': amount,
            'order_count': 1,
            'date': today,
            'created_at': firestore.SERVER_TIMESTAMP
        })

def get_daily_sales(db, store_id):
    """Get today's sales total and order count"""
    today = datetime.now().strftime("%Y-%m-%d")
    doc_ref = db.collection('stores').document(store_id).collection('daily_sales').document(today)
    
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        return data.get('total', 0), data.get('order_count', 0)
    return 0, 0

# ============================================
# AUTO CLEANUP FUNCTIONS
# ============================================
def auto_cleanup_completed_orders(db, store_id):
    """Auto delete completed orders from previous days (keep today's only)"""
    today = datetime.now().strftime("%Y-%m-%d")
    orders_ref = db.collection('stores').document(store_id).collection('orders')
    
    # Get all completed orders
    completed_orders = orders_ref.where('status', '==', 'completed').stream()
    
    deleted_count = 0
    for order in completed_orders:
        order_data = order.to_dict()
        order_timestamp = order_data.get('timestamp', '')
        
        # Check if order is from previous day (not today)
        if order_timestamp and not order_timestamp.startswith(today):
            order.reference.delete()
            deleted_count += 1
    
    if deleted_count > 0:
        load_orders.clear()
    
    return deleted_count

def auto_cleanup_old_daily_sales(db, store_id):
    """Auto delete daily_sales older than 30 days"""
    from datetime import timedelta
    
    # Calculate date 30 days ago
    cutoff_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    daily_sales_ref = db.collection('stores').document(store_id).collection('daily_sales')
    
    # Get all daily_sales documents
    all_sales = daily_sales_ref.stream()
    
    deleted_count = 0
    for sale in all_sales:
        sale_date = sale.id  # Document ID is the date (e.g., "2026-01-01")
        
        # Delete if older than 30 days
        if sale_date < cutoff_date:
            sale.reference.delete()
            deleted_count += 1
    
    return deleted_count

def run_auto_cleanup(db, store_id):
    """Run all auto cleanup tasks"""
    orders_deleted = auto_cleanup_completed_orders(db, store_id)
    sales_deleted = auto_cleanup_old_daily_sales(db, store_id)
    return orders_deleted, sales_deleted

# ============================================
# HELPER FUNCTIONS
# ============================================
def parse_price(price_str):
    """Convert price string to number for calculation"""
    myanmar_digits = '၀၁၂၃၄၅၆၇၈၉'
    english_digits = '0123456789'
    
    result = str(price_str)
    for m, e in zip(myanmar_digits, english_digits):
        result = result.replace(m, e)
    
    try:
        return int(''.join(filter(str.isdigit, result)))
    except:
        return 0


def build_offline_menu_data_url(store, categories, items):
    """
    Build a data URL containing full menu HTML so customer can view menu offline when scanning QR.
    Returns (data_url_string, byte_length) - if byte_length too large, QR may be dense.
    """
    store_name = html.escape(store.get('store_name', 'Menu'))
    subtitle = html.escape(store.get('subtitle', 'Food & Drinks'))
    logo = store.get('logo', '☕')
    if isinstance(logo, str) and logo.startswith(('http://', 'https://')):
        logo_html = f'<img src="{html.escape(logo)}" style="width:80px;height:80px;object-fit:contain;border-radius:8px;" alt="">'
    else:
        logo_html = f'<span style="font-size:3em;">{html.escape(logo)}</span>'

    cat_names = [c.get('category_name', '') for c in categories]
    cat_items = {cat: [] for cat in cat_names}
    for item in items:
        cat = item.get('category', '')
        if cat in cat_items:
            cat_items[cat].append(item)

    lines = []
    for cat in cat_names:
        if not cat_items.get(cat):
            continue
        lines.append(f'<div style="background:#8B4513;color:#fff;text-align:center;padding:8px;border-radius:10px;margin:12px 0 8px 0;font-weight:600;">{html.escape(cat)}</div>')
        for it in cat_items[cat]:
            name = html.escape(it.get('name', ''))
            price = html.escape(str(it.get('price', '')))
            lines.append(f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #eee;"><span>{name}</span><span style="color:#1E90FF;font-weight:600;">{price} Ks</span></div>')

    body_content = ''.join(lines)
    html_doc = (
        '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<style>body{font-family:sans-serif;margin:12px;background:#fff;color:#222;font-size:16px}'
        'h1{margin:0 0 4px 0;font-size:1.3em;color:#2E86AB}.sub{margin:0 0 12px 0;font-size:0.95em;color:#666}</style></head><body>'
        f'<div style="text-align:center;margin-bottom:12px;">{logo_html}</div>'
        f'<h1 style="text-align:center;">{store_name}</h1>'
        f'<p class="sub" style="text-align:center;">{subtitle}</p>'
        f'{body_content}'
        '</body></html>'
    )
    b64 = base64.b64encode(html_doc.encode('utf-8')).decode('ascii')
    data_url = 'data:text/html;base64,' + b64
    return data_url, len(data_url)


# QR code version 40 supports max ~2953 bytes. Stay under 2900 to be safe.
MAX_QR_DATA_LEN = 2900


def _make_qr_image_bytes(data_url):
    """Generate QR code image bytes from data URL. Raises if data too large for QR version 40."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )
    qr.add_data(data_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def build_offline_menu_data_url_per_category(store, category_name, items):
    """Build one data URL for a single category (for splitting when full menu is too large)."""
    store_name = html.escape(store.get('store_name', 'Menu'))
    subtitle = html.escape(store.get('subtitle', 'Food & Drinks'))
    logo = store.get('logo', '☕')
    if isinstance(logo, str) and logo.startswith(('http://', 'https://')):
        logo_html = f'<img src="{html.escape(logo)}" style="width:80px;height:80px;object-fit:contain;border-radius:8px;" alt="">'
    else:
        logo_html = f'<span style="font-size:3em;">{html.escape(logo)}</span>'
    lines = [
        f'<div style="background:#8B4513;color:#fff;text-align:center;padding:8px;border-radius:10px;margin:12px 0 8px 0;font-weight:600;">{html.escape(category_name)}</div>'
    ]
    for it in items:
        name = html.escape(it.get('name', ''))
        price = html.escape(str(it.get('price', '')))
        lines.append(f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #eee;"><span>{name}</span><span style="color:#1E90FF;font-weight:600;">{price} Ks</span></div>')
    body_content = ''.join(lines)
    html_doc = (
        '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<style>body{font-family:sans-serif;margin:12px;background:#fff;color:#222;font-size:16px}'
        'h1{margin:0 0 4px 0;font-size:1.3em;color:#2E86AB}.sub{margin:0 0 12px 0;font-size:0.95em;color:#666}</style></head><body>'
        f'<div style="text-align:center;margin-bottom:12px;">{logo_html}</div>'
        f'<h1 style="text-align:center;">{store_name}</h1>'
        f'<p class="sub" style="text-align:center;">{subtitle} — {html.escape(category_name)}</p>'
        f'{body_content}'
        '</body></html>'
    )
    b64 = base64.b64encode(html_doc.encode('utf-8')).decode('ascii')
    return 'data:text/html;base64,' + b64


def format_price(price):
    """Format price for display"""
    return f"{price:,}"

# ============================================
# SESSION STATE
# ============================================
if 'is_admin' not in st.session_state:
    st.session_state.is_admin = False
if 'current_store' not in st.session_state:
    st.session_state.current_store = None
if 'editing_id' not in st.session_state:
    st.session_state.editing_id = None
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""
if 'editing_store' not in st.session_state:
    st.session_state.editing_store = None
if 'confirm_delete_store' not in st.session_state:
    st.session_state.confirm_delete_store = None
if 'cart' not in st.session_state:
    st.session_state.cart = []
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = 'menu'
if 'table_no' not in st.session_state:
    st.session_state.table_no = ""
if 'last_pending_count' not in st.session_state:
    st.session_state.last_pending_count = 0
if 'sound_enabled' not in st.session_state:
    st.session_state.sound_enabled = True
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = True
if 'order_success' not in st.session_state:
    st.session_state.order_success = None
if 'last_order_id' not in st.session_state:
    st.session_state.last_order_id = None  # For customer: show "preparing" noti when admin marks order
if 'confirm_clear_history' not in st.session_state:
    st.session_state.confirm_clear_history = False

SUPER_ADMIN_KEY = "superadmin123"

# ============================================
# COLOR CONFIGURATION - ဒီမှာ အရောင်တွေ ပြောင်းလို့ရပါတယ်
# ============================================
COLORS = {
    # Quantity control buttons
    "minus_btn": "#6c757d",      # ➖ button color (Grey)
    "plus_btn": "#6c757d",       # ➕ button color (Grey)
    "delete_btn": "#dc3545",     # 🗑️ button color (Red)
    
    # ADD button
    "add_btn": "#FF5722",        # ADD button color (Orange)
    
    # Order button
    "order_btn_start": "#2E8B57",  # Order button gradient start (Green)
    "order_btn_end": "#9ACD32",    # Order button gradient end (Yellow-Green)
    
    # Header colors
    "header_title": "#2E86AB",   # Store name color
    "header_subtitle": "#8B4513", # Subtitle color
    
    # Category header
    "category_bg_start": "#8B4513",  # Category header gradient start
    "category_bg_end": "#A0522D",    # Category header gradient end
    
    # Total box
    "total_bg_start": "#2E86AB",  # Total box gradient start
    "total_bg_end": "#1a5276",    # Total box gradient end
}

def play_notification_sound():
    """Play notification sound for new orders"""
    # Using a simple beep sound via JavaScript
    sound_js = """
    <script>
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        
        function playBeep(freq, duration) {
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            
            oscillator.frequency.value = freq;
            oscillator.type = 'sine';
            
            gainNode.gain.setValueAtTime(0.4, audioContext.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + duration);
            
            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + duration);
        }
        
        // Play notification melody
        playBeep(880, 0.15);
        setTimeout(() => playBeep(988, 0.15), 150);
        setTimeout(() => playBeep(1047, 0.3), 300);
    </script>
    """
    components.html(sound_js, height=0)

# ============================================
# MAIN APP
# ============================================
def main():
    db = get_firebase_connection()
    
    if db is None:
        st.error("⚠️ Firebase ချိတ်ဆက်မှု မအောင်မြင်ပါ။")
        st.info("""
        **Setup လုပ်နည်း:**
        1. Firebase Console မှာ Project ဖန်တီးပါ
        2. Firestore Database ဖွင့်ပါ
        3. Service Account Key download လုပ်ပါ
        4. `firebase_credentials.json` အဖြစ် သိမ်းပါ
        """)
        return
    
    # Use db object id for caching
    db_id = id(db)
    stores = load_stores(db_id)
    
    # nza2.py လို - customer mode အတွက် CSS မထည့်ပါ (sidebar အမြဲပေါ်မယ်)
    query_params = st.query_params
    url_store_id = query_params.get("store", None)
    is_customer_mode = url_store_id is not None and not st.session_state.is_admin
    
    # Custom styling for customers (using COLORS config)
    if not st.session_state.is_admin:
        st.markdown(f"""
        <style>
        /* Make all buttons compact */
        button {{
            padding: 5px 12px !important;
            min-height: 0 !important;
            height: auto !important;
            border-radius: 8px !important;
        }}
        button p {{
            font-size: 14px !important;
            margin: 0 !important;
        }}
        
        /* ============================================ */
        /* Menu Item Row - Name left, Price right */
        /* ============================================ */
        .menu-item-row {{
            display: flex !important;
            justify-content: space-between !important;
            align-items: center !important;
            width: 100% !important;
            padding: 5px 0 !important;
        }}
        .menu-item-row .item-name {{
            font-weight: 600 !important;
            font-size: 16px !important;
            color: #333 !important;
        }}
        .menu-item-row .item-price {{
            font-size: 15px !important;
            color: #2E8B57 !important;
            font-weight: 500 !important;
        }}
        
        /* ============================================ */
        /* ADD buttons - customizable color */
        /* ============================================ */
        button[kind="secondary"] {{
            background: {COLORS["add_btn"]} !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 8px 20px !important;
            color: #fff !important;
            font-weight: 600 !important;
            font-size: 16px !important;
            min-width: auto !important;
        }}
        button[kind="secondary"]:hover {{
            opacity: 0.85 !important;
        }}
        button[kind="secondary"] p {{
            color: #fff !important;
            font-weight: 600 !important;
            font-size: 16px !important;
        }}
        /* Primary buttons - Order button */
        button[kind="primary"] {{
            background: linear-gradient(90deg, {COLORS["order_btn_start"]} 0%, {COLORS["order_btn_end"]} 100%) !important;
            border: none !important;
            border-radius: 20px !important;
        }}
        button[kind="primary"]:hover {{
            opacity: 0.9 !important;
        }}
        /* Item container style */
        div[data-testid="stVerticalBlock"] > div[data-testid="element-container"] > div[data-testid="stContainer"] {{
            border-radius: 12px !important;
            padding: 10px !important;
        }}
        
        /* ============================================ */
        /* Hide marker divs */
        /* ============================================ */
        .cart-order-marker, .cart-item-marker, .menu-item-marker, .qty-btn-marker {{
            display: none;
        }}
        
        /* ============================================ */
        /* Menu Item - Force Horizontal ALWAYS */
        /* ============================================ */
        .menu-item-marker + div[data-testid="stHorizontalBlock"] {{
            flex-wrap: nowrap !important;
            flex-direction: row !important;
            align-items: center !important;
            gap: 0 !important;
        }}
        .menu-item-marker + div[data-testid="stHorizontalBlock"] > div {{
            display: flex !important;
            align-items: center !important;
            width: auto !important;
            flex: none !important;
        }}
        .menu-item-marker + div[data-testid="stHorizontalBlock"] > div:nth-child(1) {{
            flex: 2 1 0 !important;
            min-width: 0 !important;
        }}
        .menu-item-marker + div[data-testid="stHorizontalBlock"] > div:nth-child(2) {{
            flex: 1 1 0 !important;
            min-width: 0 !important;
        }}
        .menu-item-marker + div[data-testid="stHorizontalBlock"] > div:nth-child(3) {{
            flex: 0 0 auto !important;
            justify-content: flex-end !important;
        }}
        
        /* Override Streamlit's responsive breakpoints */
        @media (max-width: 768px) {{
            .menu-item-marker + div[data-testid="stHorizontalBlock"] {{
                flex-wrap: nowrap !important;
                flex-direction: row !important;
            }}
            .menu-item-marker + div[data-testid="stHorizontalBlock"] > div {{
                width: auto !important;
            }}
        }}
        
        /* ============================================ */
        /* Cart Item Buttons - Force Horizontal on Mobile */
        /* ============================================ */
        .cart-item-marker + div[data-testid="stHorizontalBlock"] {{
            flex-wrap: nowrap !important;
            flex-direction: row !important;
            gap: 5px !important;
        }}
        .cart-item-marker + div[data-testid="stHorizontalBlock"] > div {{
            flex: none !important;
            width: auto !important;
            min-width: 0 !important;
        }}
        .cart-item-marker + div[data-testid="stHorizontalBlock"] > div:first-child {{
            flex: 2 !important;
        }}
        
        /* ============================================ */
        /* Adjacent Cart & Order buttons */
        /* ============================================ */
        .cart-order-marker + div[data-testid="stHorizontalBlock"] {{
            flex-wrap: nowrap !important;
            flex-direction: row !important;
            gap: 0 !important;
        }}
        .cart-order-marker + div[data-testid="stHorizontalBlock"] > div {{
            padding-left: 0 !important;
            padding-right: 0 !important;
            flex: 1 !important;
        }}
        /* Cart button - left rounded, white with border */
        .cart-order-marker + div[data-testid="stHorizontalBlock"] > div:first-child button {{
            border-radius: 25px 0 0 25px !important;
            border: 1px solid #ccc !important;
            border-right: none !important;
            background: #fff !important;
            color: #333 !important;
        }}
        .cart-order-marker + div[data-testid="stHorizontalBlock"] > div:first-child button:hover {{
            background: #f5f5f5 !important;
        }}
        /* Order button - right rounded, green gradient */
        .cart-order-marker + div[data-testid="stHorizontalBlock"] > div:last-child button {{
            border-radius: 0 25px 25px 0 !important;
            background: linear-gradient(90deg, {COLORS["order_btn_start"]} 0%, {COLORS["order_btn_end"]} 100%) !important;
            border: none !important;
        }}
        .cart-order-marker + div[data-testid="stHorizontalBlock"] > div:last-child button:hover {{
            opacity: 0.9 !important;
        }}
        
        /* ============================================ */
        /* 3-Column Category Layout Styling */
        /* ============================================ */
        .category-column {{
            background: #fafafa;
            border-radius: 15px;
            padding: 10px;
            margin: 5px 0;
        }}
        </style>
        """, unsafe_allow_html=True)
    
    # ============================================
    # SIDEBAR - nza2.py ပုံစံအတိုင်း (sidebar အမြဲပေါ်မယ်)
    # ============================================
    st.sidebar.title("📱 QR Code Menu System")
    
    url_table = query_params.get("table", None)
    
    if url_table:
        st.session_state.table_no = url_table
    
    current_store = None
    store_from_url = False
    
    if stores:
        store_options = {s['store_name']: s for s in stores}
        store_by_id = {s['store_id']: s for s in stores}
        
        if url_store_id and url_store_id in store_by_id:
            current_store = store_by_id[url_store_id]
            store_from_url = True
            if st.session_state.is_admin:
                selected_store_name = st.sidebar.selectbox(
                    "🏪 ဆိုင်ရွေးပါ",
                    options=list(store_options.keys()),
                    index=list(store_options.keys()).index(current_store['store_name'])
                )
                current_store = store_options[selected_store_name]
            else:
                st.sidebar.markdown(f"### 🏪 {current_store['store_name']}")
        else:
            selected_store_name = st.sidebar.selectbox(
                "🏪 ဆိုင်ရွေးပါ",
                options=list(store_options.keys())
            )
            current_store = store_options[selected_store_name]
        
        st.session_state.current_store = current_store
    else:
        st.sidebar.info("ဆိုင်မရှိသေးပါ။")
    
    st.sidebar.divider()
    
    # Admin Login - nza2.py လို (store_from_url ဆိုရင် expander၊ မဟုတ်ရင် subheader + Password + Login)
    if not st.session_state.is_admin:
        if store_from_url:
            with st.sidebar.expander("🔐 Admin Login", expanded=False):
                admin_key = st.text_input("Password", type="password", key="admin_pwd")
                if st.button("Login", use_container_width=True, key="admin_login"):
                    if admin_key == SUPER_ADMIN_KEY:
                        st.session_state.is_admin = True
                        st.session_state.is_super_admin = True
                        st.rerun()
                    elif current_store and admin_key == current_store.get('admin_key'):
                        st.session_state.is_admin = True
                        st.session_state.is_super_admin = False
                        st.rerun()
                    else:
                        st.error("❌ Password မှားနေပါတယ်။")
        else:
            st.sidebar.subheader("🔐 Admin Login")
            admin_key = st.sidebar.text_input("Password", type="password", key="admin_pwd")
            if st.sidebar.button("Login", use_container_width=True, key="admin_login"):
                if admin_key == SUPER_ADMIN_KEY:
                    st.session_state.is_admin = True
                    st.session_state.is_super_admin = True
                    st.rerun()
                elif current_store and admin_key == current_store.get('admin_key'):
                    st.session_state.is_admin = True
                    st.session_state.is_super_admin = False
                    st.rerun()
                else:
                    st.sidebar.error("❌ Password မှားနေပါတယ်။")
    else:
        if st.session_state.get('is_super_admin'):
            st.sidebar.success("👑 Super Admin Mode")
        else:
            st.sidebar.success("👨‍💼 Admin Mode")
        
        # View Mode Toggle for Admin
        st.sidebar.divider()
        view_mode = st.sidebar.radio(
            "📺 View Mode",
            ["🍽️ Menu", "🖥️ Counter Dashboard"],
            index=0 if st.session_state.view_mode == 'menu' else 1
        )
        st.session_state.view_mode = 'menu' if view_mode == "🍽️ Menu" else 'counter'
        
        if st.sidebar.button("Logout", use_container_width=True):
            st.session_state.is_admin = False
            st.session_state.is_super_admin = False
            st.session_state.editing_id = None
            st.session_state.view_mode = 'menu'
            st.rerun()
    
    # Customer Cart - moved to bottom of page for customer mode (see below in main content)
    
    # Admin Controls
    if st.session_state.is_admin and st.session_state.view_mode == 'menu':
        st.sidebar.divider()
        
        if st.session_state.get('is_super_admin'):
            with st.sidebar.expander("🏪 ဆိုင်အသစ်ထည့်ရန်", expanded=False):
                with st.form("add_store_form", clear_on_submit=True):
                    new_store_id = st.text_input("Store ID *", placeholder="naypyidaw")
                    new_store_name = st.text_input("ဆိုင်အမည် *", placeholder="နေပြည်တော်")
                    new_admin_key = st.text_input("Admin Password *", placeholder="npt123")
                    new_logo = st.text_input("Logo", value="☕")
                    new_subtitle = st.text_input("Subtitle", value="Food & Drinks")
                    st.caption("🎨 Background ရွေးပါ (တစ်ခုခုသာ):")
                    new_bg_color = st.color_picker("Background Color", value="#ffffff")
                    new_bg_image = st.text_input("Background Image URL", placeholder="https://example.com/bg.jpg")
                    
                    if st.form_submit_button("➕ ဆိုင်ထည့်မည်", use_container_width=True):
                        if new_store_id and new_store_name and new_admin_key:
                            save_store(db, {
                                'store_id': new_store_id.strip().lower(),
                                'store_name': new_store_name.strip(),
                                'admin_key': new_admin_key.strip(),
                                'logo': new_logo.strip() or '☕',
                                'subtitle': new_subtitle.strip() or 'Food & Drinks',
                                'bg_color': new_bg_color if new_bg_color != "#ffffff" else '',
                                'bg_image': new_bg_image.strip()
                            })
                            st.success(f"✅ '{new_store_name}' ထည့်ပြီးပါပြီ။")
                            st.rerun()
                        else:
                            st.error("⚠️ လိုအပ်တဲ့အချက်များ ဖြည့်ပါ။")
            
            if current_store:
                with st.sidebar.expander("📱 QR Code ထုတ်ရန်", expanded=False):
                    qr_mode = st.radio(
                        "QR အမျိုးအစား",
                        ["📴 Offline Menu QR (လိုင်းမလိုပဲ menu ကြည့်ရန်)", "🌐 Online QR (မှာယူရန် - လိုင်းလိုသည်)"],
                        index=0,
                        help="Offline QR ဖတ်ရင် menu ချက်ချင်းပေါ်မယ်။ Online QR က app ဖွင့်ပြီး မှာယူလို့ရမယ်။"
                    )
                    use_offline_qr = "Offline" in qr_mode

                    if use_offline_qr:
                        # Offline: QR contains full menu HTML (data URL) - customer လိုင်းမဖွင့်ပဲ ဖတ်လို့ရမယ်
                        categories_for_qr = load_categories(db_id, current_store['store_id'])
                        items_for_qr = load_menu_items(db_id, current_store['store_id'])
                        data_url, data_len = build_offline_menu_data_url(current_store, categories_for_qr, items_for_qr)
                        if data_len > MAX_QR_DATA_LEN:
                            st.error(f"⚠️ Menu ရှည်လွန်းပါတယ် ({data_len} လုံး)။ QR တစ်ခုတည်းနဲ့ မထုတ်နိုင်ပါ။ အောက်က 'မျိုးကွဲအလိုက် QR ထုတ်မည်' သုံးပါ။")
                        else:
                            if data_len > 2500:
                                st.warning(f"⚠️ Menu အနည်းငယ်ရှည်ပါတယ် ({data_len} လုံး)။")
                        st.caption("ဒီ QR ကို Customer ဖတ်ရင် လိုင်းမဖွင့်ပဲ menu ကြည့်လို့ရပါတယ်။")
                        if st.button("🔲 Offline QR ထုတ်မည် (menu တစ်ခုလုံး)", use_container_width=True):
                            if data_len > MAX_QR_DATA_LEN:
                                st.error("Menu ရှည်လွန်းလို့ QR တစ်ခုတည်း မထုတ်နိုင်ပါ။ မျိုးကွဲအလိုက် ထုတ်မည် ကို သုံးပါ။")
                            else:
                                qr = qrcode.QRCode(
                                    version=1,
                                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                                    box_size=8,
                                    border=2,
                                )
                                qr.add_data(data_url)
                                qr.make(fit=True)
                                qr_img = qr.make_image(fill_color="black", back_color="white")
                                buf = BytesIO()
                                qr_img.save(buf, format="PNG")
                                buf.seek(0)
                                st.image(buf, caption=f"Offline QR: {current_store['store_name']}")
                                st.download_button(
                                    label="📥 Download Offline QR",
                                    data=buf.getvalue(),
                                    file_name=f"qr_offline_{current_store['store_id']}_menu.png",
                                    mime="image/png",
                                    use_container_width=True
                                )
                        st.caption("မျိုးကွဲများလွန်းရင် အောက်က မျိုးကွဲအလိုက် QR ထုတ်ပါ။")
                        if st.button("📑 မျိုးကွဲအလိုက် Offline QR များ ထုတ်မည်", use_container_width=True):
                            cat_names = [c.get('category_name', '') for c in categories_for_qr]
                            cat_items = {cat: [] for cat in cat_names}
                            for it in items_for_qr:
                                c = it.get('category', '')
                                if c in cat_items:
                                    cat_items[c].append(it)
                            per_category = [(cat, cat_items[cat]) for cat in cat_names if cat_items.get(cat)]
                            if not per_category:
                                st.warning("ပစ္စည်းမရှိသေးပါ။")
                            else:
                                idx = 0
                                for cat_name, cat_item_list in per_category:
                                    data_url_cat = build_offline_menu_data_url_per_category(current_store, cat_name, cat_item_list)
                                    if len(data_url_cat) > MAX_QR_DATA_LEN:
                                        chunk_size = 10
                                        for i in range(0, len(cat_item_list), chunk_size):
                                            chunk = cat_item_list[i:i + chunk_size]
                                            part_label = f"{cat_name} ({i//chunk_size + 1})" if len(cat_item_list) > chunk_size else cat_name
                                            data_url_part = build_offline_menu_data_url_per_category(current_store, part_label, chunk)
                                            try:
                                                png_bytes = _make_qr_image_bytes(data_url_part)
                                                st.image(png_bytes, caption=f"Offline QR: {part_label}")
                                                safe_name = "".join(c if c.isalnum() or c in " ()" else "_" for c in part_label).strip()[:50]
                                                st.download_button(f"📥 Download {part_label}", data=png_bytes, file_name=f"qr_offline_{current_store['store_id']}_{safe_name}.png", mime="image/png", use_container_width=True, key=f"offline_qr_dl_{current_store['store_id']}_{idx}")
                                            except ValueError:
                                                st.warning(f"'{part_label}' အတွက် data ရှည်လွန်းပါသေးတယ်။")
                                            idx += 1
                                    else:
                                        try:
                                            png_bytes = _make_qr_image_bytes(data_url_cat)
                                            st.image(png_bytes, caption=f"Offline QR: {cat_name}")
                                            safe_name = "".join(c if c.isalnum() or c in " ()" else "_" for c in cat_name).strip()[:50]
                                            st.download_button(f"📥 Download {cat_name}", data=png_bytes, file_name=f"qr_offline_{current_store['store_id']}_{safe_name}.png", mime="image/png", use_container_width=True, key=f"offline_qr_dl_{current_store['store_id']}_{idx}")
                                        except ValueError:
                                            st.warning(f"'{cat_name}' အတွက် data ရှည်လွန်းပါသေးတယ်။")
                                        idx += 1
                    else:
                        # Online: QR = URL to Streamlit app (မှာယူရန်)
                        base_url = st.text_input(
                            "App URL",
                            value="https://your-app.streamlit.app",
                            help="Streamlit Cloud URL ထည့်ပါ"
                        )
                        qr_table = st.text_input("စားပွဲနံပါတ် (optional)", placeholder="5")
                        if qr_table:
                            qr_url = f"{base_url}/?store={current_store['store_id']}&table={qr_table}&embed=true"
                        else:
                            qr_url = f"{base_url}/?store={current_store['store_id']}&embed=true"
                        st.code(qr_url, language=None)
                        if st.button("🔲 Online QR ထုတ်မည်", use_container_width=True):
                            qr = qrcode.QRCode(
                                version=1,
                                error_correction=qrcode.constants.ERROR_CORRECT_L,
                                box_size=10,
                                border=4,
                            )
                            qr.add_data(qr_url)
                            qr.make(fit=True)
                            qr_img = qr.make_image(fill_color="black", back_color="white")
                            buf = BytesIO()
                            qr_img.save(buf, format="PNG")
                            buf.seek(0)
                            st.image(buf, caption=f"Online QR: {current_store['store_name']}")
                            st.download_button(
                                label="📥 Download Online QR",
                                data=buf.getvalue(),
                                file_name=f"qr_online_{current_store['store_id']}_{qr_table or 'menu'}.png",
                                mime="image/png",
                                use_container_width=True
                            )
                
                with st.sidebar.expander("⚙️ ဆိုင်ပြင်ဆင်ရန်", expanded=False):
                    st.markdown("**Store ID:**")
                    st.code(current_store['store_id'], language=None)
                    
                    st.divider()
                    st.markdown("**ဆိုင်အမည် ပြင်ရန်:**")
                    with st.form("edit_store_form"):
                        edit_store_name = st.text_input("ဆိုင်အမည်", value=current_store['store_name'])
                        edit_admin_key = st.text_input("Admin Password", value=current_store.get('admin_key', ''))
                        edit_logo = st.text_input("Logo", value=current_store.get('logo', '☕'))
                        edit_subtitle = st.text_input("Subtitle", value=current_store.get('subtitle', 'Food & Drinks'))
                        st.caption("🎨 Background ရွေးပါ (တစ်ခုခုသာ):")
                        edit_bg_color = st.color_picker("Background Color", value=current_store.get('bg_color', '#ffffff') or '#ffffff')
                        edit_bg_image = st.text_input("Background Image URL", value=current_store.get('bg_image', ''), placeholder="https://example.com/image.jpg")
                        edit_bg_counter = st.checkbox("Counter Dashboard မှာလည်း Background ပြောင်းမယ်", value=current_store.get('bg_counter', False))
                        st.caption("💡 Image ထည့်ရင် Color ထက် Image ကို ဦးစားပေးမယ်")
                        
                        if st.form_submit_button("💾 သိမ်းမည်", use_container_width=True):
                            update_store(db, current_store['store_id'], {
                                'store_name': edit_store_name.strip(),
                                'admin_key': edit_admin_key.strip(),
                                'logo': edit_logo.strip() or '☕',
                                'subtitle': edit_subtitle.strip() or 'Food & Drinks',
                                'bg_color': edit_bg_color if edit_bg_color != "#ffffff" else '',
                                'bg_image': edit_bg_image.strip(),
                                'bg_counter': edit_bg_counter
                            })
                            st.success("✅ ပြင်ဆင်ပြီးပါပြီ")
                            st.rerun()
                    
                    st.divider()
                    st.markdown("**⚠️ ဆိုင်ဖျက်ရန်:**")
                    st.warning("ဤဆိုင်နှင့် data အားလုံး ပျက်သွားပါမည်!")
                    
                    if st.session_state.confirm_delete_store == current_store['store_id']:
                        st.error(f"'{current_store['store_name']}' ကို ဖျက်မှာ သေချာပါသလား?")
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button("✅ ဟုတ်ကဲ့ ဖျက်မည်", use_container_width=True, type="primary"):
                                delete_store(db, current_store['store_id'])
                                st.session_state.confirm_delete_store = None
                                st.session_state.current_store = None
                                st.success("✅ ဆိုင်ဖျက်ပြီးပါပြီ")
                                st.rerun()
                        with col_no:
                            if st.button("❌ မဖျက်တော့ပါ", use_container_width=True):
                                st.session_state.confirm_delete_store = None
                                st.rerun()
                    else:
                        if st.button("🗑️ ဆိုင်ဖျက်မည်", use_container_width=True):
                            st.session_state.confirm_delete_store = current_store['store_id']
                            st.rerun()
        
        if current_store:
            store_id = current_store['store_id']
            categories = load_categories(db_id, store_id)
            cat_names = [c['category_name'] for c in categories]
            cat_by_name = {c['category_name']: c for c in categories}
            
            with st.sidebar.expander("📁 အမျိုးအစား စီမံရန်", expanded=False):
                new_cat = st.text_input("အမျိုးအစားအသစ်", placeholder="Desserts")
                if st.button("➕ ထည့်မည်", use_container_width=True, key="add_cat"):
                    if new_cat and new_cat.strip():
                        if new_cat.strip() not in cat_names:
                            save_category(db, store_id, new_cat.strip())
                            st.success(f"✅ '{new_cat}' ထည့်ပြီး။")
                            st.rerun()
                        else:
                            st.warning("⚠️ ရှိပြီးသားပါ။")
                
                if cat_names:
                    st.caption("လက်ရှိ အမျိုးအစားများ:")
                    for cat in cat_names:
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"• {cat}")
                        with col2:
                            if st.button("🗑️", key=f"delcat_{cat}"):
                                items = load_menu_items(db_id, store_id)
                                items_in_cat = [i for i in items if i.get('category') == cat]
                                if items_in_cat:
                                    st.error(f"⚠️ ပစ္စည်း {len(items_in_cat)} ခုရှိနေပါသည်။")
                                else:
                                    cat_data = cat_by_name.get(cat)
                                    if cat_data:
                                        delete_category(db, store_id, cat_data['id'])
                                    st.rerun()
            
            with st.sidebar.expander("➕ ပစ္စည်းအသစ်ထည့်ရန်", expanded=False):
                if cat_names:
                    with st.form("add_item_form", clear_on_submit=True):
                        item_name = st.text_input("အမည် *", placeholder="Cappuccino")
                        item_price = st.text_input("ဈေးနှုန်း *", placeholder="2500")
                        item_cat = st.selectbox("အမျိုးအစား *", cat_names)
                        
                        if st.form_submit_button("✅ ထည့်မည်", use_container_width=True):
                            if item_name and item_price:
                                save_menu_item(db, store_id, {
                                    'name': item_name.strip(),
                                    'price': item_price.strip(),
                                    'category': item_cat
                                })
                                st.success(f"✅ '{item_name}' ထည့်ပြီး။")
                                st.rerun()
                            else:
                                st.error("⚠️ အချက်အလက် ဖြည့်ပါ။")
                else:
                    st.info("အမျိုးအစား အရင်ထည့်ပါ။")
            
            items = load_menu_items(db_id, store_id)
            st.sidebar.divider()
            st.sidebar.metric("📊 ပစ္စည်းအရေအတွက်", len(items))
    
    # ============================================
    # MAIN CONTENT
    # ============================================
    if not current_store:
        st.title("📱 QR Code Menu System")
        st.info("ဆိုင်မရှိသေးပါ။ Super Admin Login ဝင်ပြီး ဆိုင်အသစ်ထည့်ပါ။")
        return
    
    store_id = current_store['store_id']
    
    # Counter Dashboard View
    if st.session_state.is_admin and st.session_state.view_mode == 'counter':
        
        # Apply background if enabled for Counter Dashboard
        if current_store.get('bg_counter', False):
            bg_image_url = current_store.get('bg_image', '')
            bg_color = current_store.get('bg_color', '')
            
            if bg_image_url:
                st.markdown(f"""
                <style>
                .stApp {{
                    background-image: url("{bg_image_url}");
                    background-size: cover;
                    background-position: center;
                    background-repeat: no-repeat;
                    background-attachment: fixed;
                }}
                .stApp::before {{
                    content: "";
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background: rgba(255, 255, 255, 0.85);
                    z-index: -1;
                }}
                </style>
                """, unsafe_allow_html=True)
            elif bg_color:
                st.markdown(f"""
                <style>
                .stApp {{
                    background-color: {bg_color} !important;
                }}
                </style>
                """, unsafe_allow_html=True)
        
        st.title("🖥️ Counter Dashboard")
        st.subheader(f"📍 {current_store['store_name']}")
        
        # Auto cleanup on dashboard load (runs once per session)
        if 'cleanup_done_today' not in st.session_state:
            st.session_state.cleanup_done_today = None
        
        today = datetime.now().strftime("%Y-%m-%d")
        if st.session_state.cleanup_done_today != today:
            orders_deleted, sales_deleted = run_auto_cleanup(db, store_id)
            st.session_state.cleanup_done_today = today
            if orders_deleted > 0 or sales_deleted > 0:
                st.toast(f"🧹 Auto Cleanup: Orders {orders_deleted} ခု၊ Sales {sales_deleted} ခု ဖျက်ပြီး")
        
        orders = load_orders(db_id, store_id)
        
        # Check for new orders and play sound
        pending_count = len([o for o in orders if o.get('status') == 'pending'])
        if st.session_state.sound_enabled and pending_count > st.session_state.last_pending_count:
            play_notification_sound()
        st.session_state.last_pending_count = pending_count
        
        # Daily Sales Total
        daily_total, daily_order_count = get_daily_sales(db, store_id)
        today_date = datetime.now().strftime("%Y-%m-%d")
        
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #2E86AB 0%, #1a5276 100%); 
                    padding: 20px; border-radius: 15px; text-align: center; margin-bottom: 20px;">
            <div style="color: #fff; font-size: 1em; opacity: 0.9;">📅 {today_date} ရောင်းရငွေ</div>
            <div style="color: #fff; font-size: 2.5em; font-weight: bold;">{format_price(daily_total)} Ks</div>
            <div style="color: #fff; font-size: 1em; opacity: 0.8; margin-top: 5px;">✅ ပြီးဆုံး Order: {daily_order_count} ခု</div>
        </div>
        """, unsafe_allow_html=True)
        
        # Filter orders by status
        col1, col2 = st.columns(2)
        with col1:
            pending_orders = [o for o in orders if o.get('status') == 'pending']
            st.metric("⏳ Pending", len(pending_orders))
        with col2:
            preparing_orders = [o for o in orders if o.get('status') == 'preparing']
            st.metric("👨‍🍳 Preparing", len(preparing_orders))
        
        st.divider()
        
        # Controls row
        col_refresh, col_sound, col_auto = st.columns(3)
        with col_refresh:
            if st.button("🔄 Refresh", use_container_width=True):
                load_orders.clear()
                st.rerun()
        with col_sound:
            sound_label = "🔔" if st.session_state.sound_enabled else "🔕"
            btn_type = "primary" if st.session_state.sound_enabled else "secondary"
            if st.button(sound_label, use_container_width=True, type=btn_type, help="Sound ON/OFF"):
                st.session_state.sound_enabled = not st.session_state.sound_enabled
                st.rerun()
        with col_auto:
            auto_label = "⏱️ Auto" if st.session_state.auto_refresh else "⏸️ Stop"
            auto_type = "primary" if st.session_state.auto_refresh else "secondary"
            if st.button(auto_label, use_container_width=True, type=auto_type, help="Auto Refresh ON/OFF"):
                st.session_state.auto_refresh = not st.session_state.auto_refresh
                st.rerun()
        
        # Auto-refresh using streamlit-autorefresh
        if st.session_state.auto_refresh:
            # Auto refresh every 10 seconds (10000 ms)
            refresh_count = st_autorefresh(interval=10000, limit=None, key="dashboard_refresh")
            if refresh_count > 0:
                load_orders.clear()  # Clear cache on refresh
            st.caption(f"🟢 Auto-refresh ON (10s) | Refresh #{refresh_count}")
        else:
            st.caption("🔴 Auto-refresh OFF - Manual refresh သာ")
        
        # Show pending and preparing orders
        active_orders = [o for o in orders if o.get('status') in ['pending', 'preparing']]
        
        if not active_orders:
            st.info("📭 လက်ရှိ order မရှိပါ")
        else:
            for order in active_orders:  # Already sorted by timestamp desc
                status_color = "🟡" if order['status'] == 'pending' else "🟠"
                
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.markdown(f"### {status_color} Order #{order['order_id']}")
                        st.markdown(f"**🪑 Table: {order['table_no']}**")
                        st.markdown(f"**📝 Items:** {order['items']}")
                        st.markdown(f"**💰 Total:** {format_price(int(order['total']))} Ks")
                        st.caption(f"🕐 {order['timestamp']}")
                    
                    with col2:
                        if order['status'] == 'pending':
                            if st.button("👨‍🍳 Preparing", key=f"prep_{order['order_id']}", use_container_width=True):
                                update_order_status(db, store_id, order['order_id'], 'preparing')
                                st.rerun()
                        
                        if st.button("✅ Complete", key=f"done_{order['order_id']}", use_container_width=True, type="primary"):
                            # Add to daily sales
                            try:
                                order_total = int(order['total'])
                                add_to_daily_sales(db, store_id, order_total)
                            except:
                                pass
                            # Mark as completed (keep for history)
                            update_order_status(db, store_id, order['order_id'], 'completed')
                            st.toast(f"✅ Order #{order['order_id']} ပြီးဆုံးပြီ!")
                            st.rerun()
        
        # ============================================
        # ORDER HISTORY
        # ============================================
        st.divider()
        
        completed_orders = [o for o in orders if o.get('status') == 'completed']
        
        with st.expander(f"📋 Order History ({len(completed_orders)} orders)", expanded=False):
            if not completed_orders:
                st.info("ပြီးဆုံးပြီးသော order မရှိသေးပါ")
            else:
                # Filter by today only
                today = datetime.now().strftime("%Y-%m-%d")
                today_completed = [o for o in completed_orders if o.get('timestamp', '').startswith(today)]
                
                st.markdown(f"**📅 ယနေ့ ({today}) - {len(today_completed)} orders**")
                
                if today_completed:
                    # Create a table view
                    for order in today_completed:
                        col1, col2, col3, col4 = st.columns([1, 2, 3, 2])
                        with col1:
                            st.write(f"🪑 **{order['table_no']}**")
                        with col2:
                            st.write(f"#{order['order_id']}")
                        with col3:
                            st.write(order['items'][:50] + "..." if len(order['items']) > 50 else order['items'])
                        with col4:
                            st.write(f"💰 {format_price(int(order['total']))} Ks")
                        st.divider()
                else:
                    st.info("ယနေ့ ပြီးဆုံးသော order မရှိသေးပါ")
                
                # Option to clear old history
                st.divider()
                col_clear, col_confirm = st.columns(2)
                with col_clear:
                    if st.button("🗑️ History ရှင်းမည်", use_container_width=True):
                        st.session_state.confirm_clear_history = True
                
                if st.session_state.get('confirm_clear_history'):
                    with col_confirm:
                        if st.button("⚠️ အတည်ပြု", use_container_width=True, type="primary"):
                            for order in completed_orders:
                                delete_order(db, store_id, order['order_id'])
                            st.session_state.confirm_clear_history = False
                            st.toast("✅ History ရှင်းပြီးပါပြီ")
                            st.rerun()
        
        return  # Don't show menu in counter mode
    
    # Menu View
    
    # Apply background (Image takes priority over Color) - စာမျက်နှာနဲ့ sidebar တစ်ရောင်တည်း
    bg_image_url = current_store.get('bg_image', '')
    bg_color = current_store.get('bg_color', '') or '#e8edd5'  # default: အောက်က အရောင် (light greenish-yellow)
    
    if bg_image_url:
        # Background Image with overlay
        st.markdown(f"""
        <style>
        .stApp {{
            background-image: url("{bg_image_url}");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
        }}
        .stApp::before {{
            content: "";
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(255, 255, 255, 0.85);
            z-index: -1;
        }}
        [data-testid="stSidebar"] > div:first-child {{
            background-color: {bg_color} !important;
        }}
        header[data-testid="stHeader"], [data-testid="stHeader"], header {{
            background-color: {bg_color} !important;
        }}
        </style>
        """, unsafe_allow_html=True)
    else:
        # Background Color - စာမျက်နှာနဲ့ sidebar အောက်က အရောင်အတိုင်း
        st.markdown(f"""
        <style>
        .stApp {{
            background-color: {bg_color} !important;
        }}
        [data-testid="stSidebar"] > div:first-child {{
            background-color: {bg_color} !important;
        }}
        /* Deploy အတန်း (header) ကိုလည်း အောက်က အရောင်အတိုင်း */
        header[data-testid="stHeader"], [data-testid="stHeader"], header {{
            background-color: {bg_color} !important;
        }}
        </style>
        """, unsafe_allow_html=True)
    
    logo_value = current_store.get('logo', '☕')
    is_image = isinstance(logo_value, str) and logo_value.startswith(('http://', 'https://'))
    
    if is_image:
        logo_html = f'<img src="{html.escape(logo_value)}" style="width:150px; height:150px; object-fit:contain; border-radius:10px;" alt="Logo">'
    else:
        logo_html = f'<span style="font-size:8em;">{logo_value}</span>'
    
    st.markdown(f"""
    <style>
    .header-container {{
        text-align: center;
        padding: 20px 0 10px 0;
    }}
    .header-logo {{
        display: flex;
        justify-content: center;
        margin-bottom: 10px;
    }}
    .header-title {{
        font-size: 3em;
        font-weight: bold;
        color: {COLORS["header_title"]};
        margin: 10px 0 5px 0;
    }}
    .header-subtitle {{
        font-size: 1.5em;
        font-weight: bold;
        color: {COLORS["header_subtitle"]};
        letter-spacing: 3px;
    }}
    </style>
    <div class="header-container">
        <div class="header-logo">{logo_html}</div>
        <div class="header-title">{html.escape(current_store['store_name'])}</div>
        <div class="header-subtitle">{html.escape(current_store.get('subtitle', 'Food & Drinks'))}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Show order success alert (ပြင်ဆင်နေပါပြီ noti ရောက်ရင် ဒီ box ပျောက်မယ်)
    if st.session_state.order_success and not st.session_state.is_admin:
        order_info = st.session_state.order_success
        order_status = get_order_status(db, current_store['store_id'], order_info['order_id']) if current_store else None
        
        if order_status in ('pending', 'preparing'):
            st_autorefresh(interval=5000, limit=None, key="customer_order_track")
        
        # စိမ်းရောင် "Order ပို့ပြီးပါပြီ!" box - pending ပဲ ပြ။ preparing/completed ရောက်ရင် မပြ
        if order_status not in ('preparing', 'completed'):
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); 
                        padding: 25px; border-radius: 15px; text-align: center; margin: 20px 0;
                        box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3);">
                <div style="display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 10px;">
                    <span style="font-size: 1.8em;">✅</span>
                    <span style="color: #fff; font-size: 1.5em; font-weight: bold;">Order ပို့ပြီးပါပြီ!</span>
                </div>
                <div style="color: #fff; font-size: 1.2em; opacity: 0.95;">
                    Order #{order_info['order_id']}
                </div>
                <div style="color: #fff; font-size: 1em; opacity: 0.9; margin-top: 10px;">
                    🪑 စားပွဲ: {order_info['table_no']} | 💰 {format_price(order_info['total'])} Ks
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # Show status to customer when admin updates (Preparing / Completed)
        if order_status == 'preparing':
            st.markdown("""
            <div style="background: linear-gradient(135deg, #f0ad4e 0%, #ec971f 100%); 
                        padding: 18px; border-radius: 12px; text-align: center; margin: 15px 0;
                        box-shadow: 0 3px 12px rgba(240, 173, 78, 0.4);">
                <div style="font-size: 2em; margin-bottom: 5px;">👨‍🍳</div>
                <div style="color: #fff; font-size: 1.3em; font-weight: bold;">
                    သင့်အော်ဒါ ပြင်ဆင်နေပါပြီ!
                </div>
                <div style="color: #fff; font-size: 0.95em; opacity: 0.95; margin-top: 5px;">
                    မကြာမီ ရောက်ပါမည်။
                </div>
            </div>
            """, unsafe_allow_html=True)
        elif order_status == 'completed':
            st.markdown("""
            <div style="background: linear-gradient(135deg, #5bc0de 0%, #46b8da 100%); 
                        padding: 18px; border-radius: 12px; text-align: center; margin: 15px 0;">
                <div style="color: #fff; font-size: 1.2em; font-weight: bold;">✅ ပြီးပါပြီ။ ကျေးဇူးတင်ပါတယ်။</div>
            </div>
            """, unsafe_allow_html=True)
        
        # Play success sound
        components.html("""
        <script>
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            function playBeep(freq, duration, delay) {
                setTimeout(() => {
                    const oscillator = audioContext.createOscillator();
                    const gainNode = audioContext.createGain();
                    oscillator.connect(gainNode);
                    gainNode.connect(audioContext.destination);
                    oscillator.frequency.value = freq;
                    oscillator.type = 'sine';
                    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
                    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + duration);
                    oscillator.start(audioContext.currentTime);
                    oscillator.stop(audioContext.currentTime + duration);
                }, delay);
            }
            // Success melody
            playBeep(523, 0.15, 0);
            playBeep(659, 0.15, 150);
            playBeep(784, 0.15, 300);
            playBeep(1047, 0.3, 450);
        </script>
        """, height=0)
        
        # Button to dismiss and order more
        if st.button("🍽️ ထပ်မှာမည်", use_container_width=True, type="primary"):
            st.session_state.order_success = None
            st.rerun()
        
        st.divider()
    
    # Show table number if set
    if st.session_state.table_no and not st.session_state.is_admin and not st.session_state.order_success:
        st.info(f"🪑 စားပွဲနံပါတ်: **{st.session_state.table_no}**")
    
    # Customer: show "preparing" notification when admin clicked Preparing for their order
    if not st.session_state.is_admin and st.session_state.last_order_id and current_store:
        orders_for_status = load_orders(db_id, store_id)
        my_order = next((o for o in orders_for_status if o.get('order_id') == st.session_state.last_order_id), None)
        status = my_order.get('status') if my_order else None

        if my_order is None:
            st.session_state.last_order_id = None
        elif status == 'completed':
            st.session_state.last_order_id = None
        elif status == 'preparing':
            load_orders.clear()
            st_autorefresh(interval=8000, limit=None, key="customer_preparing_refresh")
        elif status == 'pending':
            # Order still pending: poll so we see "preparing" when admin clicks
            load_orders.clear()
            st_autorefresh(interval=5000, limit=None, key="customer_preparing_refresh")
    
    categories = load_categories(db_id, store_id)
    items = load_menu_items(db_id, store_id)
    
    cat_names = [c['category_name'] for c in categories]
    category_items = {cat: [] for cat in cat_names}
    for item in items:
        cat = item.get('category', '')
        if cat in category_items:
            category_items[cat].append(item)
    
    if not items and not categories:
        st.info("ℹ️ ပစ္စည်းမရှိသေးပါ။ Admin Login ဝင်ပြီး ထည့်ပါ။")
    else:
        st.markdown(f"""
        <style>
        .cat-header {{
            background: linear-gradient(135deg, {COLORS["category_bg_start"]} 0%, {COLORS["category_bg_end"]} 100%);
            color: #fff;
            text-align: center;
            padding: 10px 20px;
            border-radius: 20px;
            font-size: 1.1em;
            font-weight: 600;
            margin: 10px 0 15px 0;
        }}
        </style>
        """, unsafe_allow_html=True)
        
        # ============================================
        # 3-COLUMN CATEGORY LAYOUT
        # Chinese Food (ဘယ်) | Rice (အလယ်) | Juice (ညာ)
        # Category အသစ်တွေက အောက်မှာ row အသစ်နဲ့ ဆက်သွားမည်
        # ============================================
        
        # Filter categories that have items
        active_cats = [cat for cat in cat_names if category_items.get(cat)]
        
        # Display categories in 4-column rows
        num_cols = 4
        for row_start in range(0, len(active_cats), num_cols):
            row_cats = active_cats[row_start:row_start + num_cols]
            
            # Create 3 columns for this row
            cols = st.columns(num_cols)
            
            for col_idx, col in enumerate(cols):
                if col_idx < len(row_cats):
                    cat = row_cats[col_idx]
                    cat_items = category_items.get(cat, [])
                    
                    with col:
                        # Category header
                        st.markdown(f'<div class="cat-header">{html.escape(cat)}</div>', unsafe_allow_html=True)
                        
                        # Items in this category (vertical list)
                        for item in cat_items:
                            if st.session_state.is_admin:
                                # Admin view - with border, item...dots...price
                                with st.container(border=True):
                                    st.markdown(f'''
                                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                                        <span style="font-weight:600; color:#333;">{html.escape(item['name'])}</span>
                                        <span style="flex:1; border-bottom:2px dotted #ccc; margin:0 10px;"></span>
                                        <span style="color:#1E90FF; font-weight:600; white-space:nowrap;">{item['price']} Ks</span>
                                    </div>
                                    ''', unsafe_allow_html=True)
                                    
                                    btn_col1, btn_col2 = st.columns(2)
                                    with btn_col1:
                                        if st.button("✏️", key=f"e_{item['item_id']}"):
                                            st.session_state.editing_id = item['item_id']
                                            st.rerun()
                                    with btn_col2:
                                        if st.button("🗑️", key=f"d_{item['item_id']}"):
                                            delete_menu_item(db, store_id, item['item_id'])
                                            st.rerun()
                            else:
                                # Customer view - Item...dots...Price, ADD below left
                                with st.container(border=True):
                                    st.markdown(f'''
                                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                                        <span style="font-weight:600; color:#333;">{html.escape(item['name'])}</span>
                                        <span style="flex:1; border-bottom:2px dotted #ccc; margin:0 10px;"></span>
                                        <span style="color:#1E90FF; font-weight:600; white-space:nowrap;">{item['price']} Ks</span>
                                    </div>
                                    ''', unsafe_allow_html=True)
                                    # ADD button below, left aligned (red/orange)
                                    clicked = st.button("ADD", key=f"add_{item['item_id']}", type="secondary")
                                if clicked:
                                    # Check if item already in cart
                                    found = False
                                    for cart_item in st.session_state.cart:
                                        if cart_item['item_id'] == item['item_id']:
                                            cart_item['qty'] += 1
                                            found = True
                                            break
                                    
                                    if not found:
                                        st.session_state.cart.append({
                                            'item_id': item['item_id'],
                                            'name': item['name'],
                                            'price': item['price'],
                                            'qty': 1
                                        })
                                    st.rerun()
                            
                            # Edit form for admin
                            if st.session_state.is_admin and st.session_state.editing_id == item['item_id']:
                                with st.form(f"edit_{item['item_id']}"):
                                    new_name = st.text_input("အမည်", value=item['name'])
                                    new_price = st.text_input("ဈေးနှုန်း", value=str(item['price']))
                                    cat_idx = cat_names.index(item.get('category', cat_names[0])) if item.get('category') in cat_names else 0
                                    new_cat = st.selectbox("အမျိုးအစား", cat_names, index=cat_idx)
                                    
                                    c1, c2 = st.columns(2)
                                    with c1:
                                        if st.form_submit_button("💾 သိမ်း", use_container_width=True):
                                            update_menu_item(db, store_id, item['item_id'], {
                                                'name': new_name.strip(),
                                                'price': new_price.strip(),
                                                'category': new_cat
                                            })
                                            st.session_state.editing_id = None
                                            st.rerun()
                                    with c2:
                                        if st.form_submit_button("❌ ပယ်", use_container_width=True):
                                            st.session_state.editing_id = None
                                            st.rerun()
                else:
                    # Empty column - show nothing or placeholder
                    with col:
                        st.empty()
        
    
    # ============================================
    # CUSTOMER CART (Bottom of page for mobile)
    # ============================================
    if not st.session_state.is_admin and st.session_state.cart:
        st.divider()
        st.markdown("### 🛒 မှာထားသောပစ္စည်းများ")
        
        
        total = 0
        for i, item in enumerate(st.session_state.cart):
            price = parse_price(item['price'])
            total += price * item['qty']
            
            with st.container(border=True):
                # Item name and price with dots
                st.markdown(f'''
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-weight:600; color:#333;">{html.escape(item['name'])}</span>
                    <span style="flex:1; border-bottom:2px dotted #ccc; margin:0 10px;"></span>
                    <span style="color:#1E90FF; font-weight:600;">{item['price']} Ks</span>
                </div>
                ''', unsafe_allow_html=True)
                
                # Quantity control: ➖ [qty] ➕ 🗑️ - aligned left, same size
                b1, b2, b3, b4, b5, b6 = st.columns([1, 1, 1, 0.3, 1, 2.7])
                with b1:
                    minus_clicked = st.button("➖", key=f"minus_{i}", use_container_width=True)
                with b2:
                    # Display quantity - same size as buttons, no border
                    st.markdown(f'''
                    <div style="display:flex; align-items:center; justify-content:center; 
                                background:transparent; border:none;
                                height:48px; width:100%; box-sizing:border-box;
                                font-size:20px; font-weight:bold; color:#333;">
                        {item['qty']}
                    </div>
                    ''', unsafe_allow_html=True)
                with b3:
                    plus_clicked = st.button("➕", key=f"plus_{i}", use_container_width=True)
                with b4:
                    st.empty()  # Spacer between + and delete
                with b5:
                    del_clicked = st.button("Cancel", key=f"remove_{i}", use_container_width=True)
                with b6:
                    st.empty()
                
                # Handle button clicks
                if minus_clicked:
                    if st.session_state.cart[i]['qty'] > 1:
                        st.session_state.cart[i]['qty'] -= 1
                    else:
                        st.session_state.cart.pop(i)
                    st.rerun()
                if plus_clicked:
                    st.session_state.cart[i]['qty'] += 1
                    st.rerun()
                if del_clicked:
                    st.session_state.cart.pop(i)
                    st.rerun()
        
        # Inject JavaScript to style quantity buttons (using components.html to run JS)
        # Colors from COLORS config
        minus_color = COLORS["minus_btn"]
        plus_color = COLORS["plus_btn"]
        delete_color = COLORS["delete_btn"]
        
        components.html(f"""
        <script>
            function styleQtyButtons() {{
                var doc = parent.document;
                if (!doc) return;
                
                doc.querySelectorAll('button').forEach(function(btn) {{
                    var text = btn.textContent || btn.innerText || '';
                    
                    // ➖ ➕ buttons - no color (default/light grey)
                    if (text.indexOf('➖') !== -1 || text.indexOf('➕') !== -1) {{
                        btn.style.setProperty('background', '#f0f2f6', 'important');
                        btn.style.setProperty('color', '#333', 'important');
                        btn.style.setProperty('border', '1px solid #ccc', 'important');
                        btn.style.setProperty('border-radius', '12px', 'important');
                        btn.style.setProperty('min-height', '48px', 'important');
                        btn.style.setProperty('min-width', '50px', 'important');
                        btn.style.setProperty('font-size', '18px', 'important');
                    }}
                    
                    // Cancel button - bold text
                    if (text.indexOf('Cancel') !== -1) {{
                        btn.style.setProperty('background', '#f0f2f6', 'important');
                        btn.style.setProperty('color', '#333', 'important');
                        btn.style.setProperty('border', '1px solid #ccc', 'important');
                        btn.style.setProperty('border-radius', '12px', 'important');
                        btn.style.setProperty('min-height', '48px', 'important');
                        btn.style.setProperty('min-width', '50px', 'important');
                        btn.style.setProperty('font-size', '16px', 'important');
                        btn.style.setProperty('font-weight', 'bold', 'important');
                        // Also style the p element inside button
                        var pTag = btn.querySelector('p');
                        if (pTag) {{
                            pTag.style.setProperty('font-weight', 'bold', 'important');
                            pTag.style.setProperty('color', '#333', 'important');
                        }}
                    }}
                }});
                
                // Fix column layout - aligned left with small gap
                doc.querySelectorAll('[data-testid="stHorizontalBlock"]').forEach(function(block) {{
                    var html = block.innerHTML || '';
                    if (html.indexOf('➖') !== -1 && html.indexOf('➕') !== -1) {{
                        block.style.display = 'flex';
                        block.style.flexWrap = 'nowrap';
                        block.style.gap = '8px';
                        block.style.justifyContent = 'flex-start';
                        
                        var children = block.children;
                        for (var i = 0; i < children.length; i++) {{
                            children[i].style.flex = 'none';
                            children[i].style.width = 'auto';
                            children[i].style.padding = '0';
                            children[i].style.minWidth = '0';
                        }}
                    }}
                    
                    // Cart & Order buttons - separate borders, small gap, left aligned
                    if (html.indexOf('Cart') !== -1 && html.indexOf('Order') !== -1) {{
                        block.style.display = 'flex';
                        block.style.flexWrap = 'nowrap';
                        block.style.gap = '10px';
                        block.style.justifyContent = 'flex-start';
                        
                        var children = block.children;
                        for (var i = 0; i < children.length; i++) {{
                            children[i].style.flex = 'none';
                            children[i].style.width = 'auto';
                            children[i].style.padding = '0';
                            children[i].style.minWidth = '0';
                        }}
                    }}
                }});
                
                // Style Cart & Order buttons - separate borders, same size
                doc.querySelectorAll('button').forEach(function(btn) {{
                    var text = btn.textContent || btn.innerText || '';
                    
                    // Cart button - fully rounded, own border
                    if (text.indexOf('Cart') !== -1) {{
                        btn.style.setProperty('background', '#f0f2f6', 'important');
                        btn.style.setProperty('color', '#333', 'important');
                        btn.style.setProperty('border', '2px solid #333', 'important');
                        btn.style.setProperty('border-radius', '25px', 'important');
                        btn.style.setProperty('padding', '12px 25px', 'important');
                        btn.style.setProperty('min-width', '160px', 'important');
                        btn.style.setProperty('min-height', '50px', 'important');
                        btn.style.setProperty('font-weight', 'bold', 'important');
                        var pTag = btn.querySelector('p');
                        if (pTag) {{
                            pTag.style.setProperty('font-weight', 'bold', 'important');
                            pTag.style.setProperty('color', '#333', 'important');
                        }}
                    }}
                    
                    // Order button - fully rounded, own border
                    if (text.indexOf('Order') !== -1) {{
                        btn.style.setProperty('background', 'linear-gradient(90deg, #2E8B57 0%, #9ACD32 100%)', 'important');
                        btn.style.setProperty('color', 'white', 'important');
                        btn.style.setProperty('border', '2px solid #333', 'important');
                        btn.style.setProperty('border-radius', '25px', 'important');
                        btn.style.setProperty('padding', '12px 25px', 'important');
                        btn.style.setProperty('min-width', '160px', 'important');
                        btn.style.setProperty('min-height', '50px', 'important');
                        btn.style.setProperty('font-weight', 'bold', 'important');
                        var pTag = btn.querySelector('p');
                        if (pTag) {{
                            pTag.style.setProperty('font-weight', 'bold', 'important');
                            pTag.style.setProperty('color', 'white', 'important');
                        }}
                    }}
                }});
            }}
            
            // Run multiple times
            styleQtyButtons();
            setTimeout(styleQtyButtons, 100);
            setTimeout(styleQtyButtons, 300);
            setTimeout(styleQtyButtons, 500);
            setInterval(styleQtyButtons, 800);
        </script>
        """, height=0)
        
        # Total and Order Section
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, {COLORS["total_bg_start"]} 0%, {COLORS["total_bg_end"]} 100%); 
                    padding: 15px; border-radius: 10px; text-align: center; margin: 15px 0;">
            <div style="color: #fff; font-size: 1.5em; font-weight: bold;">
                💰 Total: {format_price(total)} Ks
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Table Number
        if not st.session_state.table_no:
            table_no = st.text_input("🪑 စားပွဲနံပါတ် ထည့်ပါ", placeholder="ဥပမာ: 5", key="table_input")
            st.session_state.table_no = table_no
        else:
            st.info(f"🪑 စားပွဲနံပါတ်: **{st.session_state.table_no}**")
        
        # ============================================
        # ADJACENT BUTTONS (Cart Clear & Order) - ဘောင်ကပ်လျက်ပြ, ဘယ်ဘက်
        # ============================================
        # Marker div to identify these buttons
        st.markdown('<div class="cart-order-marker"></div>', unsafe_allow_html=True)
        
        cart_col, order_col, empty_col = st.columns([1, 1, 1])
        with cart_col:
            cart_clear = st.button("🗑️ Cart ရှင်းမည်", use_container_width=True, key="cart_clear_btn")
        with order_col:
            order_submit = st.button("📤 Order ပို့မည်", use_container_width=True, type="primary", key="order_submit_btn")
        with empty_col:
            st.empty()
        
        if cart_clear:
            st.session_state.cart = []
            st.rerun()
        
        if order_submit:
            if not st.session_state.table_no:
                st.error("⚠️ စားပွဲနံပါတ် ထည့်ပါ")
            elif not current_store:
                st.error("⚠️ ဆိုင်ရွေးပါ")
            else:
                # Save order - FAST with Firebase!
                items_str = " | ".join([f"{item['name']} x{item['qty']}" for item in st.session_state.cart])
                
                with st.spinner("📤 Order ပို့နေပါသည်..."):
                    order_id = save_order(db, current_store['store_id'], {
                        'table_no': st.session_state.table_no,
                        'items': items_str,
                        'total': str(total)
                    })
                
                # Save order success info for alert
                st.session_state.order_success = {
                    'order_id': order_id,
                    'table_no': st.session_state.table_no,
                    'total': total,
                    'items': items_str
                }
                st.session_state.last_order_id = order_id  # For "preparing" notification when admin updates
                st.session_state.cart = []
                st.balloons()
                st.rerun()
    
    # Footer - only show for admin
    if st.session_state.is_admin:
        st.divider()
        st.caption("📱 QR Code Menu System | ⚡ Powered by Firebase")

if __name__ == "__main__":
    main()
