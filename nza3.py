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

# Page config - app ဖွင့်တာနဲ့ sidebar collapsed၊ login ပြီးရင် auto collapse
st.set_page_config(
    page_title="QR Menu & Order",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="collapsed"
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
            
            # Use local credentials file or path from env (e.g. Render Secret File)
            if not initialized:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                creds_path = os.environ.get("FIREBASE_CREDENTIALS_PATH") or os.path.join(script_dir, "firebase_credentials.json")
                
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
        'active': store_data.get('active', True),
        'created_at': firestore.SERVER_TIMESTAMP
    })
    clear_all_cache()

def update_store(db, store_id, new_data):
    """Update store"""
    upd = {
        'store_name': new_data['store_name'],
        'admin_key': new_data['admin_key'],
        'logo': new_data.get('logo', '☕'),
        'subtitle': new_data.get('subtitle', 'Food & Drinks'),
        'bg_color': new_data.get('bg_color', ''),
        'bg_image': new_data.get('bg_image', ''),
        'bg_counter': new_data.get('bg_counter', False),
    }
    if 'active' in new_data:
        upd['active'] = new_data['active']
    for key in ('header_title_font_style', 'header_title_font_size', 'header_title_color',
                'header_subtitle_font_style', 'header_subtitle_font_size', 'header_subtitle_color',
                'category_box_bg_start', 'category_box_bg_end', 'category_box_font_color'):
        if key in new_data:
            upd[key] = new_data[key]
    db.collection('stores').document(store_id).update(upd)
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

def get_order_doc(db, store_id, order_id):
    """Get full order document for customer (status + unavailable_items message)"""
    doc = db.collection('stores').document(store_id).collection('orders').document(order_id).get()
    if doc.exists:
        return doc.to_dict()
    return None

def update_order_unavailable(db, store_id, order_id, unavailable_items_str, adjusted_total=None):
    """Save admin's 'ကုန်သွားသော ပစ္စည်းများ' and optional adjusted_total for customer."""
    upd = {'unavailable_items': (unavailable_items_str or '').strip()}
    if adjusted_total is not None:
        upd['adjusted_total'] = str(int(adjusted_total))
    db.collection('stores').document(store_id).collection('orders').document(order_id).update(upd)
    load_orders.clear()

def parse_order_items(items_str):
    """Parse order items string 'A x1 | B x2' into list of (display_text, item_name, qty)."""
    if not (items_str or '').strip():
        return []
    out = []
    for part in (items_str or '').split('|'):
        part = part.strip()
        if not part:
            continue
        # "ပန်းပွင့်စိမ်းကြော် x1" -> name, qty
        if ' x' in part and part.rstrip()[-1].isdigit():
            name = part.rsplit(' x', 1)[0].strip()
            try:
                qty = int(''.join(c for c in part.rsplit(' x', 1)[1].strip() if c.isdigit()) or '1')
            except:
                qty = 1
        else:
            name = part
            qty = 1
        out.append((part, name, qty))
    return out

def compute_adjusted_total(order_total_int, menu_items, unavailable_item_names_with_qty):
    """unavailable_item_names_with_qty = [(item_name, qty), ...]. Returns (adjusted_total, subtracted)."""
    name_to_price = {}
    for m in (menu_items or []):
        nm = (m.get('name') or '').strip()
        if nm:
            name_to_price[nm] = parse_price(m.get('price', 0))
    subtract = 0
    for item_name, qty in (unavailable_item_names_with_qty or []):
        p = name_to_price.get((item_name or '').strip(), 0)
        subtract += p * qty
    adjusted = max(0, order_total_int - subtract)
    return adjusted, subtract

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


def clear_all_daily_sales(db, store_id):
    """နေ့စဉ်ရောင်းရငွေ အားလုံး ဖျက် (စမ်းသပ်အတွက်)"""
    ref = db.collection('stores').document(store_id).collection('daily_sales')
    deleted = 0
    for doc in ref.stream():
        doc.reference.delete()
        deleted += 1
    return deleted


def load_daily_sales_history(db, store_id, last_n_days=365):
    """နေ့စဉ်ရောင်းရငွေ စာရင်း - ရက်စွဲ၊ တန်ဖိုး၊ order အရေအတွက်။ last_n_days=1 ဆိုရင် ယနေ့တစ်ရက်တည်း"""
    from datetime import timedelta
    today = datetime.now().strftime("%Y-%m-%d")
    if last_n_days == 1:
        # ယနေ့ ရွေးရင် ယနေ့တစ်ရက်ပဲ
        cutoff_start = today
        cutoff_end = today
    else:
        cutoff_start = (datetime.now() - timedelta(days=last_n_days)).strftime("%Y-%m-%d")
        cutoff_end = today
    ref = db.collection('stores').document(store_id).collection('daily_sales')
    docs = ref.stream()
    out = []
    for doc in docs:
        if cutoff_start <= doc.id <= cutoff_end:
            d = doc.to_dict()
            out.append({
                'date': doc.id,
                'total': d.get('total', 0),
                'order_count': d.get('order_count', 0)
            })
    out.sort(key=lambda x: x['date'], reverse=True)
    return out


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
    """Auto delete daily_sales older than 400 days (တစ်နှစ်ထက် ရှေးကျတာပဲ ဖျက် - နေ့စဉ်ရောင်းရငွေ ၁နှစ်ပြမယ်)"""
    from datetime import timedelta
    
    cutoff_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
    
    daily_sales_ref = db.collection('stores').document(store_id).collection('daily_sales')
    
    # Get all daily_sales documents
    all_sales = daily_sales_ref.stream()
    
    deleted_count = 0
    for sale in all_sales:
        sale_date = sale.id  # Document ID is the date (e.g., "2026-01-01")
        
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


def format_price(price):
    """Format price for display"""
    return f"{price:,}"


def _uploaded_image_to_data_url(uploaded_file, max_kb=200):
    """ကွန်ပျူတာက တင်ထားတဲ့ ပုံကို base64 data URL ပြောင်း (Firestore အတွက် အရွယ်အစား ကန့်သတ်)"""
    if uploaded_file is None:
        return None
    data = uploaded_file.read()
    if len(data) > max_kb * 1024:
        return None
    b64 = base64.b64encode(data).decode("ascii")
    mime = uploaded_file.type or "image/png"
    return f"data:{mime};base64,{b64}"


def _is_image_url(val):
    """ဒီ value က ပုံ URL (သို့) data URL လား"""
    if not isinstance(val, str) or not val:
        return False
    return val.startswith(("http://", "https://", "data:"))

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
if 'sa_confirm_delete' not in st.session_state:
    st.session_state.sa_confirm_delete = None
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
if 'preparing_sound_played' not in st.session_state:
    st.session_state.preparing_sound_played = None  # order_id that we already played preparing sound for
if 'collapse_sidebar_after_login' not in st.session_state:
    st.session_state.collapse_sidebar_after_login = False  # login ပြီးရင် sidebar auto collapse
if 'sidebar_collapsed_on_load' not in st.session_state:
    st.session_state.sidebar_collapsed_on_load = False  # page ဖွင့်ဖွင့်ချင်း sidebar auto collapse တစ်ခါပဲ
if 'collapse_on_counter_view' not in st.session_state:
    st.session_state.collapse_on_counter_view = False  # Counter နှိပ်ပြီး ဒီ view ရောက်ရင် sidebar ပိတ်မယ်
if 'confirm_clear_history' not in st.session_state:
    st.session_state.confirm_clear_history = False
if 'confirm_clear_all_history' not in st.session_state:
    st.session_state.confirm_clear_all_history = False

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
    
    # Page ဖွင့်ဖွင့်ချင်း sidebar auto collapse (customer mode မဟုတ်ရင် တစ်ခါပဲ)
    if not is_customer_mode and not st.session_state.sidebar_collapsed_on_load:
        st.session_state.collapse_sidebar_after_login = True
        st.session_state.sidebar_collapsed_on_load = True
    
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
    st.sidebar.title("📱 QR Menu & Order")
    
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
                        st.session_state.collapse_sidebar_after_login = True
                        st.rerun()
                    elif current_store and admin_key == current_store.get('admin_key'):
                        st.session_state.is_admin = True
                        st.session_state.is_super_admin = False
                        st.session_state.collapse_sidebar_after_login = True
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
                    st.session_state.collapse_sidebar_after_login = True
                    st.rerun()
                elif current_store and admin_key == current_store.get('admin_key'):
                    st.session_state.is_admin = True
                    st.session_state.is_super_admin = False
                    st.session_state.collapse_sidebar_after_login = True
                    st.rerun()
                else:
                    st.sidebar.error("❌ Password မှားနေပါတယ်။")
    else:
        if st.session_state.get('is_super_admin'):
            st.sidebar.success("👑 Super Admin Mode")
        else:
            st.sidebar.success("👨‍💼 Admin Mode")
        
        # View Mode Toggle for Admin (အဝိုင်းမဟုတ်ပဲ စာသားနှိပ်လည်း ပြောင်းအောင် button သုံး)
        st.sidebar.divider()
        st.sidebar.caption("📺 View Mode")
        # Super Admin မှာ Counter Dashboard မရှိတော့ လမ်းလွဲမရအောင် counter ဆိုရင် menu ပြောင်း
        if st.session_state.get('is_super_admin') and st.session_state.view_mode == 'counter':
            st.session_state.view_mode = 'menu'
        if st.session_state.get('is_super_admin'):
            # Super Admin အတွက် Counter Dashboard မပါဘူး - Menu နဲ့ Super Admin ပဲ
            v_menu = st.session_state.view_mode == 'menu'
            v_super = st.session_state.view_mode == 'superadmin'
            col_a, col_b = st.sidebar.columns(2)
            with col_a:
                if st.button("🍽️ Menu", use_container_width=True, type="primary" if v_menu else "secondary", key="vm_menu"):
                    st.session_state.collapse_sidebar_after_login = True  # Menu နှိပ်တာနဲ့ sidebar auto collapse
                    if not v_menu:
                        st.session_state.view_mode = 'menu'
                    st.rerun()
            with col_b:
                if st.button("👑 Super Admin", use_container_width=True, type="primary" if v_super else "secondary", key="vm_superadmin"):
                    st.session_state.collapse_sidebar_after_login = True  # Super Admin နှိပ်တာနဲ့ sidebar auto collapse
                    if not v_super:
                        st.session_state.view_mode = 'superadmin'
                    st.rerun()
        else:
            v_menu = st.session_state.view_mode == 'menu'
            v_counter = st.session_state.view_mode == 'counter'
            col_a, col_b = st.sidebar.columns(2)
            with col_a:
                if st.button("🍽️ Menu", use_container_width=True, type="primary" if v_menu else "secondary", key="vm_menu"):
                    st.session_state.collapse_sidebar_after_login = True  # Menu နှိပ်တာနဲ့ sidebar auto collapse
                    if not v_menu:
                        st.session_state.view_mode = 'menu'
                    st.rerun()
            with col_b:
                if st.button("🖥️ Counter", use_container_width=True, type="primary" if v_counter else "secondary", key="vm_counter"):
                    st.session_state.collapse_on_counter_view = True  # Counter view ရောက်ရင် sidebar ပိတ်မယ် (တစ်ကြိမ်ပဲ)
                    if not v_counter:
                        st.session_state.view_mode = 'counter'
                    st.rerun()
        
        if st.sidebar.button("Logout", use_container_width=True):
            st.session_state.collapse_sidebar_after_login = True
            st.session_state.is_admin = False
            st.session_state.is_super_admin = False
            st.session_state.editing_id = None
            st.session_state.view_mode = 'menu'
            st.rerun()
    
    # Login / View mode ပြောင်း / Logout ပြီးတိုင်း sidebar auto collapse (တစ်ကြိမ်ပဲ - မှန်မှန်ပိတ်အောင်)
    if st.session_state.get('collapse_sidebar_after_login'):
        st.session_state.collapse_sidebar_after_login = False
        components.html("""
        <script>
        (function(){
            setTimeout(function(){
                var doc = (typeof parent !== 'undefined' && parent.document) ? parent.document : document;
                if (!doc) return;
                var el = doc.querySelector('[data-testid="collapsedControl"]');
                if (!el) el = doc.querySelector('[data-testid="stSidebarCollapsedControl"]');
                if (el) { el.click(); return; }
                var sidebar = doc.querySelector('section[data-testid="stSidebar"]');
                if (sidebar) { var btn = sidebar.querySelector('button[aria-label]'); if (btn) btn.click(); }
            }, 250);
        })();
        </script>
        """, height=0)
    
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
                    new_subtitle = st.text_input("Subtitle", value="Food & Drinks")
                    new_bg_color = st.color_picker("Background Color", value="#ffffff")
                    new_active = st.checkbox("ဆိုင်ဖွင့်မည် (Active)", value=True, help="ပိတ်ထားရင် ဆိုင်က စာရင်းမှာ ပိတ်ထားသလို ပြမယ်")
                    if st.form_submit_button("➕ ဆိုင်ထည့်မည်", use_container_width=True):
                        if new_store_id and new_store_name and new_admin_key:
                            save_store(db, {
                                'store_id': new_store_id.strip().lower(),
                                'store_name': new_store_name.strip(),
                                'admin_key': new_admin_key.strip(),
                                'logo': '☕',
                                'subtitle': new_subtitle.strip() or 'Food & Drinks',
                                'bg_color': new_bg_color if new_bg_color != "#ffffff" else '',
                                'bg_image': '',
                                'active': new_active
                            })
                            st.success(f"✅ '{new_store_name}' ထည့်ပြီးပါပြီ။")
                            st.rerun()
                        else:
                            st.error("⚠️ လိုအပ်တဲ့အချက်များ ဖြည့်ပါ။")
            
            if current_store:
                with st.sidebar.expander("📱 QR Code ထုတ်ရန်", expanded=False):
                    # Online QR only (offline QR ဖြုတ်ပြီး)
                    base_url = st.text_input(
                        "App URL",
                        value="https://naingzawaung1990-cpu.github.io/menu-link",
                        help="ကိုယ့်လင့် (သို့) Streamlit Cloud URL ထည့်ပါ — ကိုယ့်လင့်သုံးရင် ပျက်ရင် backup ပြောင်းလို့ရမယ်"
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
                        edit_subtitle = st.text_input("Subtitle", value=current_store.get('subtitle', 'Food & Drinks'))
                        edit_bg_color = st.color_picker("Background Color", value=current_store.get('bg_color', '#ffffff') or '#ffffff')
                        edit_bg_counter = st.checkbox("Counter Dashboard မှာလည်း Background ပြောင်းမယ်", value=current_store.get('bg_counter', False))
                        edit_active = st.checkbox("ဆိုင်ဖွင့်မည် (Active)", value=current_store.get('active', True), help="ပိတ်ထားရင် ဆိုင်က စာရင်းမှာ ပိတ်ထားသလို ပြမယ်")
                        edit_header_payload = {}
                        if st.session_state.get('is_super_admin'):
                            st.divider()
                            st.markdown("**ခေါင်းစဉ် ၂ ခု ပြင်ဆင်ရန် (Font / Size / Color)**")
                            _font_opts = [
                                ("Default (sans-serif)", "sans-serif"),
                                ("Serif", "serif"),
                                ("Monospace", "monospace"),
                                ("Cursive", "cursive"),
                                ("Arial", "Arial, sans-serif"),
                                ("Helvetica", "Helvetica, sans-serif"),
                                ("Times New Roman", "Times New Roman, serif"),
                                ("Georgia", "Georgia, serif"),
                                ("Verdana", "Verdana, sans-serif"),
                                ("Tahoma", "Tahoma, sans-serif"),
                                ("Trebuchet MS", "Trebuchet MS, sans-serif"),
                                ("Courier New", "Courier New, monospace"),
                                ("Comic Sans MS", "Comic Sans MS, cursive"),
                                ("Impact", "Impact, sans-serif"),
                                ("Lucida Sans", "Lucida Sans Unicode, sans-serif"),
                                ("Palatino", "Palatino Linotype, serif"),
                                ("Garamond", "Garamond, serif"),
                                ("— မြန်မာ Font —", "sans-serif"),
                                ("Myanmar3", "Myanmar3, sans-serif"),
                                ("Padauk", "Padauk, sans-serif"),
                                ("Noto Sans Myanmar", "Noto Sans Myanmar, sans-serif"),
                                ("TharLon", "TharLon, sans-serif"),
                                ("Pyidaungsu", "Pyidaungsu, sans-serif"),
                                ("Masterpiece Uni Sans", "Masterpiece Uni Sans, sans-serif"),
                                ("Yunghkio", "Yunghkio, sans-serif"),
                                ("Myanmar Text", "Myanmar Text, sans-serif"),
                                ("— Ayar မြန်မာ (လှသော) —", "sans-serif"),
                                ("Ayar", "Ayar, sans-serif"),
                                ("Ayar Takhu", "Ayar Takhu, sans-serif"),
                                ("Ayar Kasone", "Ayar Kasone, sans-serif"),
                                ("Ayar Nayon", "Ayar Nayon, sans-serif"),
                                ("Ayar Wazo", "Ayar Wazo, sans-serif"),
                                ("Ayar Wagaung", "Ayar Wagaung, sans-serif"),
                                ("Ayar Tathalin", "Ayar Tathalin, sans-serif"),
                                ("Ayar Thidingyut", "Ayar Thidingyut, sans-serif"),
                                ("Ayar Tanzaungmone", "Ayar Tanzaungmone, sans-serif"),
                                ("Ayar Juno", "Ayar Juno, sans-serif"),
                                ("Ayar Typewriter", "Ayar Typewriter, sans-serif"),
                            ]
                            _font_labels = [x[0] for x in _font_opts]
                            _font_vals = [x[1] for x in _font_opts]
                            st.markdown("*ဆိုင်အမည် (ခေါင်းစဉ်)*")
                            _tit_style = current_store.get('header_title_font_style') or 'sans-serif'
                            edit_title_font_style = st.selectbox("Font style", _font_labels, index=_font_vals.index(_tit_style) if _tit_style in _font_vals else 0, key="tit_font_style")
                            edit_title_font_size = st.text_input("Font size", value=current_store.get('header_title_font_size') or '3em', placeholder="3em or 48px", key="tit_font_size")
                            edit_title_color = st.color_picker("Color", value=current_store.get('header_title_color') or COLORS["header_title"], key="tit_color")
                            st.markdown("*Subtitle*")
                            _sub_style = current_store.get('header_subtitle_font_style') or 'sans-serif'
                            edit_subtitle_font_style = st.selectbox("Font style", _font_labels, index=_font_vals.index(_sub_style) if _sub_style in _font_vals else 0, key="sub_font_style")
                            edit_subtitle_font_size = st.text_input("Font size", value=current_store.get('header_subtitle_font_size') or '1.5em', placeholder="1.5em or 24px", key="sub_font_size")
                            edit_subtitle_color = st.color_picker("Color", value=current_store.get('header_subtitle_color') or COLORS["header_subtitle"], key="sub_color")
                            edit_header_payload = {
                                'header_title_font_style': _font_vals[_font_labels.index(edit_title_font_style)],
                                'header_title_font_size': (edit_title_font_size or '3em').strip(),
                                'header_title_color': edit_title_color,
                                'header_subtitle_font_style': _font_vals[_font_labels.index(edit_subtitle_font_style)],
                                'header_subtitle_font_size': (edit_subtitle_font_size or '1.5em').strip(),
                                'header_subtitle_color': edit_subtitle_color,
                            }
                            st.divider()
                            st.markdown("**အမျိုးအစား box နဲ့ စာရောင်**")
                            edit_cat_bg_start = st.color_picker("အမျိုးအစား box နောက်ခံ (စရောင်)", value=current_store.get('category_box_bg_start') or COLORS["category_bg_start"], key="cat_bg_start")
                            edit_cat_bg_end = st.color_picker("အမျိုးအစား box နောက်ခံ (ဆုံးရောင်)", value=current_store.get('category_box_bg_end') or COLORS["category_bg_end"], key="cat_bg_end")
                            edit_cat_font_color = st.color_picker("အမျိုးအစား box စာရောင်", value=current_store.get('category_box_font_color') or '#ffffff', key="cat_font_color")
                            edit_header_payload['category_box_bg_start'] = edit_cat_bg_start
                            edit_header_payload['category_box_bg_end'] = edit_cat_bg_end
                            edit_header_payload['category_box_font_color'] = edit_cat_font_color
                        if st.form_submit_button("💾 သိမ်းမည်", use_container_width=True):
                            payload = {
                                'store_name': edit_store_name.strip(),
                                'admin_key': edit_admin_key.strip(),
                                'logo': current_store.get('logo', '☕'),
                                'subtitle': edit_subtitle.strip() or 'Food & Drinks',
                                'bg_color': edit_bg_color if edit_bg_color != "#ffffff" else '',
                                'bg_image': current_store.get('bg_image', ''),
                                'bg_counter': edit_bg_counter,
                                'active': edit_active
                            }
                            payload.update(edit_header_payload)
                            update_store(db, current_store['store_id'], payload)
                            clear_all_cache()
                            # သိမ်းပြီးနောက် store ကို ပြန်ယူပြီး session မှာ ထည့်မယ် — ခေါင်းစဉ် ပြောင်းလဲမှု ချက်ချင်းပြမယ်
                            stores_after = load_stores(db_id)
                            for s in stores_after:
                                if s.get('store_id') == current_store['store_id']:
                                    st.session_state.current_store = s
                                    break
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
    # Super Admin Dashboard (all stores overview)
    if st.session_state.get('is_super_admin') and st.session_state.get('view_mode') == 'superadmin':
        st.title("👑 Super Admin Dashboard")
        st.caption("ဆိုင်အားလုံး စာရင်း၊ ယနေ့ ရောင်းရငွေ၊ Active ဖွင့်/ပိတ်")
        db = firestore.client()
        all_stores = load_stores(db_id)
        today = datetime.now().strftime("%Y-%m-%d")
        total_sales_today = 0
        total_orders_today = 0
        active_count = sum(1 for s in all_stores if s.get('active', True))
        for s in all_stores:
            hist = load_daily_sales_history(db, s['store_id'], last_n_days=1)
            day = hist[0] if hist and hist[0]['date'] == today else None
            s['_today_total'] = day['total'] if day else 0
            s['_today_orders'] = day['order_count'] if day else 0
            total_sales_today += s['_today_total']
            total_orders_today += s['_today_orders']

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("စုစုပေါင်း ဆိုင်", len(all_stores))
        with c2:
            st.metric("ဖွင့်ထားသော ဆိုင် (Active)", active_count)
        with c3:
            st.metric("ယနေ့ စုစုပေါင်း ရောင်းရငွေ", f"{total_sales_today:,.0f} Ks")
        st.divider()

        # စာရင်း စီ/ရှာပြီး ပြခြင်း
        sa_search = st.text_input("🔍 ဆိုင်ရှာရန် (အမည် / Store ID)", placeholder="ရိုက်ထည့်ပါ...", key="sa_search")
        sa_sort = st.selectbox(
            "စီမံရန်",
            ["ဆိုင်အမည်အလိုက်", "ယနေ့ ရောင်းရငွေ များစွာ", "ယနေ့ Order များစွာ", "ဖွင့်ထားသော ဆိုင်ရင် အရင်"],
            key="sa_sort"
        )
        filtered = all_stores
        if sa_search and sa_search.strip():
            q = sa_search.strip().lower()
            filtered = [s for s in all_stores if q in (s.get('store_name') or '').lower() or q in (s.get('store_id') or '').lower()]
        if sa_sort == "ဆိုင်အမည်အလိုက်":
            filtered = sorted(filtered, key=lambda s: (s.get('store_name') or '').lower())
        elif sa_sort == "ယနေ့ ရောင်းရငွေ များစွာ":
            filtered = sorted(filtered, key=lambda s: s.get('_today_total', 0), reverse=True)
        elif sa_sort == "ယနေ့ Order များစွာ":
            filtered = sorted(filtered, key=lambda s: s.get('_today_orders', 0), reverse=True)
        elif sa_sort == "ဖွင့်ထားသော ဆိုင်ရင် အရင်":
            filtered = sorted(filtered, key=lambda s: (not s.get('active', True), (s.get('store_name') or '').lower()))

        for s in filtered:
            is_active = s.get('active', True)
            label = f"{s['store_name']} ({s['store_id']}) {'🟢' if is_active else '🔴'}"
            with st.expander(label, expanded=False):
                pw = s.get('admin_key', '') or ''
                st.text(f"Store ID: {s['store_id']}")
                st.text(f"Password: {pw}")
                st.text(f"Active: {'ဖွင့်ထား' if is_active else 'ပိတ်ထား'}")
                st.text(f"ယနေ့ ရောင်းရငွေ: {s['_today_total']:,.0f} Ks | ယနေ့ Order: {s['_today_orders']}")
                if st.session_state.get('sa_confirm_delete') == s['store_id']:
                    st.warning(f"'{s['store_name']}' ကို ဖျက်မှာ သေချာပါသလား? (ဆိုင်နဲ့ data အားလုံး ပျက်သွားပါမည်)")
                    col_yes, col_no = st.columns(2)
                    with col_yes:
                        if st.button("✅ ဟုတ်ကဲ့ ဖျက်မည်", key=f"sa_del_yes_{s['store_id']}", use_container_width=True, type="primary"):
                            delete_store(db, s['store_id'])
                            st.session_state.sa_confirm_delete = None
                            st.rerun()
                    with col_no:
                        if st.button("❌ မဖျက်တော့ပါ", key=f"sa_del_no_{s['store_id']}", use_container_width=True):
                            st.session_state.sa_confirm_delete = None
                            st.rerun()
                else:
                    btn_edit, btn_qr, btn_toggle, btn_del = st.columns(4)
                    with btn_edit:
                        if st.button("ပြင်မည်", key=f"sa_edit_{s['store_id']}", use_container_width=True):
                            st.session_state.current_store = s
                            st.session_state.view_mode = 'menu'
                            load_stores.clear()
                            st.rerun()
                    with btn_qr:
                        if st.button("QR", key=f"sa_qr_{s['store_id']}", use_container_width=True):
                            st.session_state.current_store = s
                            st.session_state.view_mode = 'menu'
                            load_stores.clear()
                            st.rerun()
                    with btn_toggle:
                        toggle_label = "ပိတ်မည်" if is_active else "ဖွင့်မည်"
                        if st.button(toggle_label, key=f"sa_toggle_{s['store_id']}", use_container_width=True):
                            update_store(db, s['store_id'], {
                                'store_name': s['store_name'],
                                'admin_key': s.get('admin_key', ''),
                                'logo': s.get('logo', '☕'),
                                'subtitle': s.get('subtitle', ''),
                                'bg_color': s.get('bg_color', ''),
                                'bg_image': s.get('bg_image', ''),
                                'bg_counter': s.get('bg_counter', False),
                                'active': not is_active
                            })
                            load_stores.clear()
                            st.rerun()
                    with btn_del:
                        if st.button("🗑️ ဖျက်မည်", key=f"sa_del_{s['store_id']}", use_container_width=True):
                            st.session_state.sa_confirm_delete = s['store_id']
                            st.rerun()
        if not all_stores:
            st.info("ဆိုင်မရှိသေးပါ။ Menu view သို့သွားပြီး ဆိုင်အသစ်ထည့်ပါ။")
        elif sa_search and sa_search.strip() and not filtered:
            st.warning("ရှာတွေ့ခြင်း မရှိပါ။")
        return
    
    if not current_store:
        st.title("📱 QR Menu & Order")
        st.info("ဆိုင်မရှိသေးပါ။ Super Admin Login ဝင်ပြီး ဆိုင်အသစ်ထည့်ပါ။")
        return
    
    store_id = current_store['store_id']
    
    # Counter Dashboard View
    if st.session_state.is_admin and st.session_state.view_mode == 'counter':
        # Counter နှိပ်လိုက်တာနဲ့ sidebar auto collapse (view ရောက်ပြီးမှ ပိတ်မယ် - တစ်ကြိမ်ပဲ)
        if st.session_state.get('collapse_on_counter_view'):
            st.session_state.collapse_on_counter_view = False
            components.html("""
            <script>
            (function(){
                setTimeout(function(){
                    var d = (typeof parent !== 'undefined' && parent.document) ? parent.document : document;
                    if (!d) return;
                    var e = d.querySelector('[data-testid="collapsedControl"]') || d.querySelector('[data-testid="stSidebarCollapsedControl"]');
                    if (e) { e.click(); return; }
                    var s = d.querySelector('section[data-testid="stSidebar"]');
                    if (s) { var b = s.querySelector('button[aria-label]'); if (b) b.click(); }
                }, 350);
            })();
            </script>
            """, height=0)
        # Apply background if enabled for Counter Dashboard
        if current_store.get('bg_counter', False):
            bg_color = current_store.get('bg_color', '')
            if bg_color:
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
        
        # ပထမပုံစံ: နေ့စဉ်ရောင်းရငွေ ရွေးချယ်မှု + expander (ဒုတိယပုံ ယနေ့ကတ်ပြား မထည့်တော့ပါ)
        period_options = {
            "ယနေ့": 1,
            "တစ်ပတ် (၇ ရက်)": 7,
            "တစ်လ (၃၀ရက်)": 30,
            "တစ်နှစ် (၃၆၅ ရက်)": 365,
        }
        period_label = st.selectbox(
            "📊 နေ့စဉ်ရောင်းရငွေ ကြည့်မယ်",
            options=list(period_options.keys()),
            index=1,
            key="sales_period"
        )
        days = period_options[period_label]
        sales_list = load_daily_sales_history(db, store_id, last_n_days=days)
        grand_total = sum(s['total'] for s in sales_list)
        grand_orders = sum(s['order_count'] for s in sales_list)
        # အပေါ်က စုစုပေါင်း - bold + အနီရောင် (expander label မှာ HTML မရလို့ သီးသန့်ပြမယ်)
        st.markdown(
            f"<div style='margin-bottom:6px'><strong>စုစုပေါင်း:</strong> <span style='color:#c0392b;font-weight:700'>{format_price(grand_total)} Ks</span></div>",
            unsafe_allow_html=True
        )
        # နှိပ်မှ ဖွင့်အောင် expanded=False (refresh ၁၀စက္ကန့်မှာ မဖွင့်သွားအောင်)
        with st.expander("📅 ရက်စွဲအလိုက် ကြည့်မယ်", expanded=False):
            if not sales_list:
                st.info("ဒီကာလအတွင်း ရောင်းရငွေ မရှိသေးပါ။")
            else:
                st.markdown(
                    f"<strong>စုစုပေါင်း:</strong> <span style='color:#c0392b;font-weight:700'>{format_price(grand_total)} Ks</span>",
                    unsafe_allow_html=True
                )
                st.divider()
                for s in sales_list:
                    # ရက်စွဲ YYYY-MM-DD -> DD-MM-YYYY
                    parts = s['date'].split('-')
                    date_display = f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 else s['date']
                    col1, col2, col3 = st.columns([2, 2, 2])
                    with col1:
                        st.write(f"📅 **{date_display}**")
                    with col2:
                        st.write(f"**{format_price(s['total'])} Ks**")
                    with col3:
                        st.write(f"✅ {s['order_count']} ခု")
                    st.divider()
        
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
                        order_display_total = int(order.get('adjusted_total') or order['total'])
                        st.markdown(f"### {status_color} Order #{order['order_id']}")
                        st.markdown(f"**🪑 Table: {order['table_no']}**")
                        st.markdown(f"**📝 Items:** {order['items']}")
                        st.markdown(f"**💰 Total:** {format_price(order_display_total)} Ks" + (" _(မရနိုင်နုတ်ပြီး)_" if order.get('adjusted_total') else ""))
                        st.caption(f"🕐 {order['timestamp']}")
                        # ကုန်သွားသော ပစ္စည်း ရွေးပါ — admin နှိပ်မှ ပွင့်မယ် (refresh မှာ မပွင့်ဘူး)
                        unav_str = (order.get('unavailable_items') or '').strip()
                        unav_set = set(n.strip() for n in unav_str.replace('၊', ',').split(',') if n.strip())
                        parsed = parse_order_items(order.get('items', ''))
                        menu_items = load_menu_items(0, store_id)
                        with st.expander("🔴 ပစ္စည်း ရနိုင်/မရနိုင် ရွေးပါ (နှိပ်ပါ)", expanded=False):
                            st.caption(f"Order #{order['order_id']} | 🪑 Table {order['table_no']}")
                            checked = []
                            for idx, row in enumerate(parsed):
                                display_text = row[0]
                                item_name = row[1]
                                qty = row[2] if len(row) > 2 else 1
                                is_unav = st.checkbox(
                                    f"မရနိုင် — {display_text}",
                                    value=(item_name in unav_set),
                                    key=f"unav_{order['order_id']}_{idx}"
                                )
                                if is_unav:
                                    checked.append((item_name, qty))
                            st.caption("မရနိုင် အမှန်ခြစ်ထားပြီး **Preparing** နှိပ်လိုက်ရင် Customer ဆီ ကုန်သွားပါပြီ တောင်ပန်းပါတယ် ပို့မည်။ Total မှ နုတ်မည်။ (သတင်းသိမ်း မလိုပါ။)")
                    
                    with col2:
                        if order['status'] == 'pending':
                            if st.button("👨‍🍳 Preparing", key=f"prep_{order['order_id']}", use_container_width=True):
                                # Preparing နှိပ်တဲ့အခါ လက်ရှိ မရနိုင် အမှန်ခြစ်ထားတာကို ယူပြီး order မှာ သိမ်း + status ပြောင်း (နောက် ၁ နာရီ/နောက်နေ့ စာရင်းမှ မပါ)
                                unav_names = ", ".join(n for n, q in checked)
                                try:
                                    orig_total = int(order['total'])
                                except:
                                    orig_total = 0
                                adjusted, _ = compute_adjusted_total(orig_total, menu_items, checked)
                                update_order_unavailable(db, store_id, order['order_id'], unav_names, adjusted)
                                update_order_status(db, store_id, order['order_id'], 'preparing')
                                st.toast("Preparing ပြီး။ Customer ဆီ မရနိုင်သတင်း ပို့ပြီး Total နုတ်ပြီး။")
                                st.rerun()
                        
                        if st.button("✅ Complete", key=f"done_{order['order_id']}", use_container_width=True, type="primary"):
                            # Add to daily sales (use adjusted_total if customer had unavailable items)
                            try:
                                order_total = int(order.get('adjusted_total') or order['total'])
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
        
        # စမ်းသပ်အတွက် History ပြန်ဖျက်မည် (Order History + နေ့စဉ်ရောင်းရငွေ အားလုံး)
        st.divider()
        with st.expander("⚠️ စမ်းသပ်အတွက် History ပြန်ဖျက်မည်", expanded=False):
            st.caption("Order History နဲ့ နေ့စဉ်ရောင်းရငွေ စာရင်း အားလုံး ဖျက်ပစ်မယ်။ စမ်းနေတဲ့အခါသာ သုံးပါ။")
            if not st.session_state.get('confirm_clear_all_history'):
                if st.button("🗑️ History အားလုံး ပြန်ဖျက်မည်", use_container_width=True, type="secondary"):
                    st.session_state.confirm_clear_all_history = True
                    st.rerun()
            else:
                st.warning("သေချာပါသလား? Order History နဲ့ နေ့စဉ်ရောင်းရငွေ အားလုံး ပျက်သွားပါမယ်။")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ ဟုတ်ကဲ့ ဖျက်မည်", use_container_width=True, type="primary"):
                        # Order History ဖျက်
                        for order in completed_orders:
                            delete_order(db, store_id, order['order_id'])
                        # နေ့စဉ်ရောင်းရငွေ ဖျက်
                        sales_deleted = clear_all_daily_sales(db, store_id)
                        st.session_state.confirm_clear_all_history = False
                        st.toast(f"✅ History အားလုံး ဖျက်ပြီး (နေ့စဉ်ရောင်းရငွေ {sales_deleted} ရက်)")
                        st.rerun()
                with c2:
                    if st.button("❌ မဖျက်တော့ပါ", use_container_width=True):
                        st.session_state.confirm_clear_all_history = False
                        st.rerun()
        
        return  # Don't show menu in counter mode
    
    # Menu View
    
    # Apply background (အရောင်ပဲ — ပုံ မသုံးပါ)
    bg_color = current_store.get('bg_color', '') or '#e8edd5'  # default: light greenish-yellow
    st.markdown(f"""
    <style>
    .stApp {{
        background-color: {bg_color} !important;
        padding-top: 0 !important;
    }}
    [data-testid="stAppViewContainer"] {{
        padding-top: 0.5rem !important;
    }}
    [data-testid="stSidebar"] > div:first-child {{
        background-color: {bg_color} !important;
    }}
    header[data-testid="stHeader"], [data-testid="stHeader"], header {{
        background-color: {bg_color} !important;
    }}
    .block-container {{
        padding-top: 0.5rem !important;
        max-width: 100%;
        overflow: visible !important;
    }}
    [data-testid="stMarkdown"]:has(.header-wrapper-outer) {{ overflow: visible !important; max-width: none !important; }}
    </style>
    """, unsafe_allow_html=True)
    
    # မြန်မာဖောင့် ပြောင်းလို့ရအောင် Google Fonts မှ သွင်း (Noto Sans Myanmar, Padauk) — စက်မှာ မထည့်ထားလည်း ပြောင်းမယ်
    st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Myanmar:wght@400;700&family=Padauk:wght@400;700&display=swap" rel="stylesheet">
    """, unsafe_allow_html=True)
    # ဆိုင်ပုံ/logoပြပါ — ဆိုင်အမည်နဲ့ subtitle ပဲ ပြ (Super Admin က ပြင်ထားတဲ့ font/size/color သုံး)
    _tit_font = current_store.get('header_title_font_style') or 'sans-serif'
    _tit_size = current_store.get('header_title_font_size') or '3em'
    _tit_color = current_store.get('header_title_color') or COLORS["header_title"]
    _sub_font = current_store.get('header_subtitle_font_style') or 'sans-serif'
    _sub_size = current_store.get('header_subtitle_font_size') or '1.5em'
    _sub_color = current_store.get('header_subtitle_color') or COLORS["header_subtitle"]
    st.markdown(f"""
    <style>
    /* ခေါင်းစဉ် ဖြတ်မပြအောင် Streamlit content width ကို ကျော်ပြီး viewport အပြည့် နေရာယူ */
    .header-wrapper-outer {{
        width: 100vw;
        position: relative;
        left: 50%;
        right: 50%;
        margin-left: -50vw !important;
        margin-right: -50vw !important;
        overflow: visible !important;
        box-sizing: border-box;
    }}
    .header-container {{
        text-align: center;
        padding: 14px 0 12px 0;
        width: 100%;
        max-width: 100%;
        overflow: visible !important;
        box-sizing: border-box;
    }}
    /* မြန်မာစာ အမြင့်သရ/အမှတ် မဖြတ်အောင် line-height နဲ့ padding */
    .header-title {{
        font-family: {_tit_font};
        font-size: {_tit_size};
        font-weight: bold;
        color: {_tit_color};
        margin: 10px 0 5px 0;
        white-space: normal;
        word-wrap: break-word;
        overflow-wrap: break-word;
        overflow: visible !important;
        max-width: 100%;
        line-height: 1.5 !important;
        padding-top: 0.2em;
        padding-bottom: 0.1em;
    }}
    .header-subtitle {{
        font-family: {_sub_font};
        font-size: {_sub_size};
        font-weight: bold;
        color: {_sub_color};
        letter-spacing: 3px;
        line-height: 1.4;
    }}
    </style>
    <div class="header-wrapper-outer">
        <div class="header-container">
            <div class="header-title">{html.escape(current_store['store_name'])}</div>
            <div class="header-subtitle">{html.escape(current_store.get('subtitle', 'Food & Drinks'))}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Show order success alert (ပြင်ဆင်နေပါပြီ noti ရောက်ရင် ဒီ box ပျောက်မယ်)
    if st.session_state.order_success and not st.session_state.is_admin:
        # မှာပြီးတာနဲ့ အပေါ်ကို လိမ့်စေ - noti ချက်ချင်းမြင်ရအောင်
        components.html("""
        <script>
        (function(){
            var scrollToTop = function(){
                try { window.scrollTo(0, 0); } catch(e) {}
                try { document.documentElement.scrollTop = 0; document.body.scrollTop = 0; } catch(e) {}
                try {
                    var doc = (typeof parent !== 'undefined' && parent.document) ? parent.document : document;
                    var root = doc.querySelector('[data-testid="stAppViewContainer"]') || doc.querySelector('.main');
                    if (root) root.scrollTop = 0;
                    if (typeof parent !== 'undefined' && parent.window) parent.window.scrollTo(0, 0);
                } catch(e) {}
            };
            scrollToTop();
            setTimeout(scrollToTop, 100);
            setTimeout(scrollToTop, 400);
        })();
        </script>
        """, height=0)
        
        order_info = st.session_state.order_success
        order_doc = get_order_doc(db, current_store['store_id'], order_info['order_id']) if current_store else None
        order_status = order_doc.get('status') if order_doc else None
        unavailable_items = (order_doc.get('unavailable_items') or '').strip() if order_doc else ''
        adjusted_total = order_doc.get('adjusted_total') if order_doc else None
        display_total = int(adjusted_total) if adjusted_total is not None else order_info['total']
        
        # Customer order status စစ်ဖို့ refresh — preparing ဆိုရင် ခဏခဏ မလုပ်အောင် interval ကြာပါမယ်
        if order_status == 'pending':
            st_autorefresh(interval=5000, limit=None, key="customer_order_track")
        elif order_status == 'preparing':
            st_autorefresh(interval=20000, limit=None, key="customer_order_track")  # ၂၀ စက္ကန့် တစ်ခါ (အသံမထပ်အောင်)
        
        # အနီရောင် noti ဖယ်ထား — မရနိုင်သတင်းက အဝါ box ထဲမှာပဲ ပြီးသား
        # စိမ်းရောင် "Order ပို့ပြီးပါပြီ!" box - pending ပဲ ပြ။ preparing/completed ရောက်ရင် မပြ (စုစုပေါင်း = adjusted ရှိရင် ပြ)
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
                    🪑 စားပွဲ: {order_info['table_no']} | 💰 {format_price(display_total)} Ks
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # Show status to customer when admin updates (Preparing / Completed) — အဝါရောင် box (အကုန်ရရင်/မရရင် နှစ်မျိုးလုံး မပျက်အောင်)
        if order_status == 'preparing':
            table_amt = f'Table: {html.escape(str(order_info["table_no"]))} | Amount: {format_price(display_total)} Ks'
            if unavailable_items:
                unav_esc = html.escape(unavailable_items)
                inner = f'<div style="color:#fff;font-size:1.3em;font-weight:bold;">သင့် order ပြင်ဆင်နေပါပြီး!</div><div style="color:#fff;font-size:1em;margin-top:8px;"><span style="color:#dc3545;font-weight:bold;">{unav_esc}</span> မရနိုင်လို့ တောင်းပန်ပါတယ်။</div><div style="color:#fff;font-size:1em;margin-top:8px;">{table_amt}</div><div style="color:#fff;font-size:0.95em;opacity:0.95;margin-top:8px;">မကြာမီ ရောက်လာပါမည်။</div>'
            else:
                inner = f'<div style="color:#fff;font-size:1.3em;font-weight:bold;">သင့် order ပြင်ဆင်နေပါပြီး!</div><div style="color:#fff;font-size:1em;margin-top:8px;">{table_amt}</div><div style="color:#fff;font-size:0.95em;opacity:0.95;margin-top:8px;">မကြာမီ ရောက်လာပါမည်။</div>'
            box_html = '<div style="background:linear-gradient(135deg,#f0ad4e 0%,#ec971f 100%);padding:18px;border-radius:12px;text-align:center;margin:15px 0;box-shadow:0 3px 12px rgba(240,173,78,0.4);"><div style="font-size:2em;margin-bottom:5px;">👨‍🍳</div>' + inner + '</div>'
            st.markdown(box_html, unsafe_allow_html=True)
            # ပြင်ဆင်နေပါပြီ noti အသံ - တစ်ကြိမ်ပဲ (localStorage နဲ့ စစ်ပြီး refresh ဖြစ်လည်း မထပ်အောင်)
            oid = order_info['order_id']
            components.html(f"""
                <script>
                    (function(){{
                        var key = 'preparing_sound_' + {json.dumps(oid)};
                        if (window.localStorage && localStorage.getItem(key)) return;
                        if (window.localStorage) localStorage.setItem(key, '1');
                        var ac = new (window.AudioContext || window.webkitAudioContext)();
                        function beep(freq, dur, delay) {{
                            setTimeout(function() {{
                                var o = ac.createOscillator();
                                var g = ac.createGain();
                                o.connect(g); g.connect(ac.destination);
                                o.frequency.value = freq;
                                o.type = 'sine';
                                g.gain.setValueAtTime(0.25, ac.currentTime);
                                g.gain.exponentialRampToValueAtTime(0.01, ac.currentTime + dur);
                                o.start(ac.currentTime);
                                o.stop(ac.currentTime + dur);
                            }}, delay);
                        }}
                        beep(587, 0.12, 0);
                        beep(784, 0.12, 120);
                        beep(988, 0.2, 240);
                    }})();
                </script>
            """, height=0)
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
            st_autorefresh(interval=20000, limit=None, key="customer_preparing_refresh")  # ၂၀ စက္ကန့် တစ်ခါ
        elif status == 'pending':
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
        _cat_bg_start = current_store.get('category_box_bg_start') or COLORS["category_bg_start"]
        _cat_bg_end = current_store.get('category_box_bg_end') or COLORS["category_bg_end"]
        _cat_font_color = current_store.get('category_box_font_color') or '#ffffff'
        st.markdown(f"""
        <style>
        .cat-header {{
            background: linear-gradient(135deg, {_cat_bg_start} 0%, {_cat_bg_end} 100%);
            color: {_cat_font_color};
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
        st.caption("📱 QR Menu & Order | ⚡ Powered by Firebase")

if __name__ == "__main__":
    main()
