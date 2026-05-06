"""
PakOrderBot — Agent Nodes v3
Fixes:
  1. Professional Urdu "not found" messages — no generic fallback
  2. Order flow: items collected → ask "koi aur cheez?" → modifications → THEN personal info
  3. Offers: direct DB query, no LLM hallucination
  4. Full conversation history preserved entire session
  5. Role from JWT only — never from user message
"""
import os, json, asyncio, random, string
from difflib import get_close_matches
from groq import AsyncGroq
from dotenv import load_dotenv
load_dotenv()
from .db_executor import execute_plan
from .state import AgentState

MODEL       = "llama-3.3-70b-versatile"
groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
JSON_RULE   = "Respond ONLY with valid JSON. No markdown, no extra text."

STAFF_ONLY = {"menu_write","offers_write","order_update","analytics_read","customer_read"}
CUSTOMER_CANCEL = {"order_cancel"}  # customers can cancel their own order


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _oid():
    return "PKT-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))

async def _menu_names():
    r = await execute_plan({"operation":"find","collection":"menu",
                             "filter":{"available":True},"projection":{"name":1},"limit":200})
    return [d["name"].lower() for d in r.get("results",[])] if r["ok"] else []

def _fuzzy(name, valid):
    n = name.lower().strip()
    if n in valid: return n
    m = get_close_matches(n, valid, n=1, cutoff=0.60)
    return m[0] if m else n

async def _get_menu_context():
    """Fetch current menu items and return a concise string for LLM context."""
    try:
        r = await execute_plan({"operation":"find","collection":"menu",
                                 "filter":{"available":True},"projection":{"name":1,"price":1,"category":1}})
        if not r["ok"] or not r["results"]:
            return "Menu is currently empty in the database."
        items = [f"{i['name']} (Rs {i.get('price',0)})" for i in r["results"]]
        return "Available Menu Items: " + ", ".join(items)
    except Exception as e:
        return f"Menu context unavailable (Error: {str(e)})"

async def _enrich(items):
    names   = [i.get("name","").lower() for i in items if i.get("name")]
    valid   = await _menu_names()
    resolved= [_fuzzy(n, valid) for n in names]
    r = await execute_plan({"operation":"find","collection":"menu",
                             "filter":{"name":{"$in":resolved},"available":True},"limit":100})
    mmap = {d["name"]:d for d in r.get("results",[])} if r["ok"] else {}
    enriched, total, max_prep, unavail = [], 0.0, 0, []
    for item, res in zip(items, resolved):
        qty = max(1, item.get("qty") or 1)
        if res not in mmap:
            unavail.append(item.get("name", res).title()); continue
        mi = mmap[res]; price = mi.get("price",0); sub = round(price*qty,2)
        pt = mi.get("prep_time", 15)           # real prep_time from menu DB
        total += sub
        if pt > max_prep: max_prep = pt
        enriched.append({"name":res,"qty":qty,"price":price,"subtotal":sub,
                          "prep_time":pt,"notes":item.get("notes")})
    if max_prep == 0: max_prep = 20            # absolute fallback only if DB had no prep_time at all
    delivery_time = 10                         # fixed delivery leg
    return enriched, round(total,2), max_prep, delivery_time, unavail


def _cart_summary(draft):
    """Short cart summary for 'koi aur cheez?' message."""
    lines = ["### 🛒 Aapka Cart:\n"]
    for it in draft.get("items",[]):
        lines.append(f"- {it['qty']}x **{it['name'].title()}** — Rs {it['subtotal']:,.0f}")
    lines.append(f"\n**💰 Total: Rs {draft.get('total',0):,.0f}**")
    lines.append("\n*Koi aur cheez add karni hai?* (haan / nahi)")
    return "\n".join(lines)


def _bill(draft):
    PAY = {"cash":"Cash on Delivery","easypaisa":"EasyPaisa","jazzcash":"JazzCash","card":"Card"}
    lines = [
        "### 🍛 PakOrderBot Bill",
        "---",
        f"- **Order ID**: `#{draft.get('order_id','?')}`",
        f"- **Naam**: {(draft.get('customer_name') or 'Mehman').title()}",
        f"- **Phone**: {draft.get('customer_phone') or '—'}",
        f"- **Address**: {draft.get('customer_address') or '—'}",
        "---",
        "#### Items:"
    ]
    for it in draft.get("items",[]):
        lines.append(f"- {it['qty']}x **{it['name'].title()}** — Rs {it['subtotal']:,.0f}")
    lines += [
        "---",
        f"- 💰 **TOTAL**: **Rs {draft.get('total',0):,.0f}**",
        f"- 🕐 **ETA**: ~{draft.get('eta',30)} minutes",
        f"- 💳 **Payment**: {PAY.get(draft.get('payment_method','cash'),'Cash on Delivery')}",
        "",
        "✅ Confirm ke liye → **YES**",
        "❌ Cancel ke liye → **NO**"
    ]
    return "\n".join(lines)


def _menu_display(items):
    EMOJI = {"main course":"🍛","starter":"🥙","side":"🫓","drink":"🥤","dessert":"🍮"}
    cats  = {}
    for it in items: cats.setdefault(it.get("category","other"),[]).append(it)
    lines = ["### 🍽️ HAMARA MENU\n---"]
    for cat, citems in cats.items():
        lines += [f"#### {EMOJI.get(cat,'🍴')} {cat.upper()}"]
        for it in citems:
            av = "✅" if it.get("available") else "❌"
            lines.append(f"- {av} **{it.get('name','').title()}** — Rs {it.get('price',0):,.0f} *({it.get('prep_time',0)} min)*")
            if it.get("description"):
                lines.append(f"  > {it['description']}")
        lines.append("")
    lines.append("💬 Order karne ke liye: *'2 chicken biryani order karo'*")
    return "\n".join(lines)


def _offers_display(offers):
    if not offers:
        return ("😔 Maafi! Abhi tak koi special offer ya deal available nahi hai.\n"
                "Jaldi hi nayi deals aa rahi hain — dobara check karte rahein! 🙏")
    
    # Filter only active offers if we didn't already
    active_offers = [o for o in offers if o.get("active", True)]
    if not active_offers:
        return ("😔 Maafi! Is waqt koi active offer available nahi hai.\n"
                "Nayi deals ke liye check karte rahein! 🙏")

    lines = ["### 🎉 SPECIAL OFFERS & DEALS\n---"]
    for o in active_offers:
        title = o.get("title", "Special Deal").upper()
        lines.append(f"#### 🔥 **{title}**")
        
        # ── Description / Discount Text ──
        # Handle both backend 'description' and frontend 'discount' (which is often used as desc)
        desc = o.get("description") or o.get("discount") or ""
        if desc:
            lines.append(f"> {desc}")
        
        # ── Items ──
        its = o.get("items")
        if its:
            if isinstance(its, list):
                if its: lines.append(f"- 📦 **Items**: {', '.join(its).title()}")
            elif isinstance(its, str) and its.strip():
                lines.append(f"- 📦 **Items**: {its.title()}")

        # ── Percent / Price ──
        pct = o.get("discount_pct")
        if pct:
            lines.append(f"- 💰 **{pct}% OFF!**")
        
        price = o.get("deal_price")
        if price:
            lines.append(f"- 💰 Deal Price: **Rs {price:,.0f}**")
            
        # ── Validity ──
        until = o.get("valid_until")
        if until:
            lines.append(f"- ⏰ Valid till: {until}")
            
        lines.append("\n---")
    
    lines.append("\n💬 Order karne ke liye: *'Friday special deal order karo'*")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Professional "not found" messages
# ─────────────────────────────────────────────────────────────────────────────

NOT_FOUND_MENU  = ("😔 Maafi! Yeh item abhi ہمارے menu mein available nahi.\n"
                   "'menu dikhao' likh kar poora menu dekh sakte hain. 🙏")
NOT_FOUND_OFFER = ("😔 Maafi! Abhi koi special offer ya deal available nahi hai.\n"
                   "Jaldi hi nayi deals aa rahi hain — dobara check karte rahein! 🙏")
NOT_FOUND_ORDER = ("❓ Maafi! Is ID ya number se koi order nahi mila.\n"
                   "Order ID check karein (e.g. PKT-XXXX) ya doosra number try karein. 🙏")
NOT_FOUND_GENERIC = "😔 Maafi! Is waqt yeh maloomat available nahi hai. Baad mein try karein. 🙏"

EMPTY_MAP = {
    "show full menu":        NOT_FOUND_MENU,
    "check menu":            NOT_FOUND_MENU,
    "menu_read":            NOT_FOUND_MENU,
    "show_menu":            NOT_FOUND_MENU,
    "show deals":            NOT_FOUND_OFFER,
    "show offers":           NOT_FOUND_OFFER,
    "track order":           NOT_FOUND_ORDER,
    "check order":           NOT_FOUND_ORDER,
    "daily order count":     "📭 Aaj abhi tak koi order nahi aaya.",
    "top selling":           "📭 Is period mein koi order record nahi.",
    "customer history":      "👤 Is number ka account nahi mila.",
}


# ─────────────────────────────────────────────────────────────────────────────
#  Prompts
# ─────────────────────────────────────────────────────────────────────────────

DATE_RULES = """
DATE PLACEHOLDERS (never hardcode dates):
  __TODAY_START__     = today 00:00:00 UTC
  __TODAY_END__       = today 23:59:59 UTC
  __YESTERDAY_START__ = yesterday start
  __WEEK_START__      = 7 days ago start
  __MONTH_START__     = first of current month
  __HOUR_AGO__        = 1 hour ago
  __NOW__             = exact current UTC timestamp (use this for status_updated_at/created_at)
"""

ROUTER_PROMPT = f"""
You are the intent classifier for PakOrderBot — a Pakistani restaurant AI.
{JSON_RULE}

CUSTOMER INTENTS (no login needed):
  menu_read      → show menu, check item price/availability
  popular_items  → customer asks which food is most ordered/famous/popular (e.g. "konsa item famous hai", "most ordered dish", "popular food", "sabse zyada log kya order karte hain", "kya recommend karo", "best dish")
  offers_read    → show offers, deals, discounts
  order_place    → place a brand NEW order (no order ID mentioned)
  order_modify   → add or remove items from an EXISTING placed order (order ID mentioned)
  order_track    → check status/ETA of OWN order only
  order_cancel   → cancel OWN order only
  feedback_write → customer submits feedback/review/complaint/compliment about food or service.
                   Trigger on: "feedback", "review", "shikayat", "complain", "tarif", "bura laga",
                   "acha laga", "maza nahi aya", "bhot acha tha", "price zyada hai", any sentence
                   describing their experience with food, service or price.
                   Extract all mentioned items as separate sentences in "message". If customer gives
                   a rating (1-5 or words like "acha"=4, "bhot acha"=5, "bura"=2, "theek"=3) set rating.
  conversation   → greetings, general restaurant questions, food recommendations

STRICT CUSTOMER RESTRICTIONS — if customer asks for ANY of these, use conversation intent and set action="access_denied_customer":
  - Other customers' orders (any order not belonging to them)
  - Menu editing / adding / removing / pricing changes
  - Staff functions: analytics, reports, revenue, daily totals
  - Customer database / customer list / other users' info
  - Offer management (adding/editing/deleting offers)
  - Order status updates (preparing/ready/dispatched/delivered) — staff only

CRITICAL RULES:
- If customer mentions an ORDER ID (PKT-XXXX) AND wants to add/remove items → order_modify
- If customer mentions an ORDER ID AND wants to cancel → order_cancel
- If customer mentions an ORDER ID AND just asking status → order_track
- order_update is ONLY for staff — NEVER for customers
- "cancel" is ALWAYS order_cancel, NEVER order_update
- Famous/popular food question → menu_read (query by most ordered from analytics)

STAFF INTENTS (require login — server enforces):
  menu_write     → add new item, update price/description/availability, disable/enable item
  offers_write   → create new offer/deal, update, disable/enable offer by name/title
  order_update   → mark order as preparing/ready/dispatched/delivered
  analytics_read → ANY of: today/week/month sales, revenue, profit, top items, all orders,
                   daily report, weekly report, monthly report, pending orders list,
                   customer order history, total earnings, business performance, top customers
  customer_read  → look up specific customer by phone or name, list all customers,
                   customer feedback (feedback collection = customer_read with action: feedback),
                   customer list with order details

STAFF INTENT ROUTING RULES:

SALES/REVENUE/REPORT — many Urdu synonyms, handle ALL of them:
- TODAY sales: "aaj ki sale","aj ki sale","aj ke sales","aaj ke sales","today sales","aaj ka revenue","aj kitni sale","aaj kitni kamai","din ki sale","aj din ki report","aaj ki kamai","aj ka hisaab" → analytics_read, action: daily_report, period: today
- WEEK sales: "is hafte ki sale","hafte ki kamai","weekly sales","weekly report","is week ki kamai","hafte mein kitna" → analytics_read, action: weekly_report, period: week
- MONTH sales: "mahine ki sale","mahine ki kamai","monthly report","is mahine ki bikri","mahine mein kitna kamaya" → analytics_read, action: monthly_report, period: month
- RULE: ANY message with (sale/sales/kamai/revenue/report/bikri/income/hisaab) + (aaj/aj/din/today) → daily_report; + (hafte/week) → weekly_report; + (mahine/month) → monthly_report

ORDERS:
- "aaj ke orders","sab orders dikhao","orders ki detail","har order ki detail","orders list" → analytics_read, action: all_orders, period: today
- "pending orders","abhi ke orders","active orders","jo orders pending hain" → analytics_read, action: pending_orders

TOP ITEMS/PRODUCTS:
- "top items","op item","konsa item","best seller","sabse zyada bikne wala","top selling product","konsa dish zyada bika","popular item","top dish","sab se popular" → analytics_read, action: top_items (use week as default period)

TOP CUSTOMERS:
- "top customer","sabse zyada order","best customer","regular customer","loyal customer" → analytics_read, action: top_customers

PROFIT/REVENUE SUMMARY:
- "total revenue","kitna kamaya","munafa","profit","total kamai","total income" → analytics_read, action: revenue_summary, period: today

CUSTOMER queries:
- "customer list","sab customers","customers dikhao","customer ka data","customer detail","customers along with orders","customer info","customers ke baare mein" → customer_read, action: list_customers
- "customer X ke orders","X ki order history","X ne kya order kiya" → customer_read, action: customer_orders; put name in customer_name field
- "customer feedback","feedback dikhao","reviews","customer reviews" → customer_read, action: feedback
- "top customer","sabse zyada order","kis customer nai zyda order","loyal customer","regular customer" → analytics_read, action: top_customers

CRITICAL for customer name queries:
- If staff gives a NAME (not phone) and asks for orders/history → customer_read, action: customer_orders, put the name in customer_name
- If staff gives a NAME and asks about their personal details → customer_read, action: list_customers (will search by name)
- Example: "asif ali k order history" → customer_read, action: customer_orders, customer_name: "asif ali"
- Example: "asif ali ki detail" → customer_read, action: list_customers, customer_name: "asif ali"

MENU/OFFER management:
- "order PKT-XXXX dikhao" (staff viewing) → analytics_read, action: order_detail
- menu add/update/disable/enable item → menu_write
- "offer/deal enable","offer/deal disable","X offer band karo","X deal chalao" → offers_write; ALWAYS put offer name/title in offer_item.title; action = "enable" or "disable"
- offer/deal create/add → offers_write

CRITICAL RULE: "cancel" is ALWAYS order_cancel (customer intent), NEVER order_update.
order_update is ONLY for staff marking orders as preparing/ready/dispatched/delivered.

OUTPUT:
{{
  "tasks": [{{
    "intent": "<intent>",
    "action": "<daily_report|weekly_report|monthly_report|top_items|top_customers|all_orders|pending_orders|revenue_summary|order_detail|list_customers|feedback|enable|disable|submit|out_of_scope|or short description>",
    "customer_name":    "<lowercase or null>",
    "customer_phone":   "<phone or null>",
    "customer_address": "<address or null>",
    "order_id":         "<PKT-XXXX or null>",
    "items":            [{{"name":"<lowercase>","qty":<int>,"notes":"<or null>"}}],
    "remove_items":     [{{"name":"<lowercase>"}}],
    "new_status":       "<received|preparing|ready|dispatched|delivered|cancelled or null>",
    "payment_method":   "<cash|easypaisa|jazzcash|card or null>",
    "notes":            "<or null>",
    "period":           "<today|week|month or null>",
    "menu_item":        {{}},
    "offer_item":       {{"title":"<exact offer title from user or null>","active":<true|false or omit>}},
    "feedback_message": "<full feedback text combining all complaints and compliments, or null>",
    "feedback_rating":  <1-5 integer or null>
  }}]
}}

RULES:
- item names and customer_name MUST be lowercase
- If user says "mera order" with no ID, set order_id null
- conversation skips DB entirely
- For order_modify: put items to ADD in "items" field, items to REMOVE in "remove_items" field
- For analytics: set action to the specific report type and period accordingly
- For staff viewing orders: action="all_orders" (today), "pending_orders", or "order_detail"
- For menu_write with multiple items: create separate tasks per item
- For offer enable/disable: ALWAYS put the offer name/title in offer_item.title field
- "friday deal disable", "sunday offer band karo" → offers_write with offer_item.title = "friday deal"/"sunday offer" and action = "disable"/"enable"

OUT-OF-SCOPE RULE (CRITICAL):
If the user asks about ANYTHING not related to this restaurant — e.g. general knowledge, politics,
weather, news, sports, coding, math, science, other businesses, jokes, creative writing, medical
advice, geography, history, AI/technology questions, personal advice — set:
  intent: "conversation", action: "out_of_scope"
This applies to BOTH customers and staff. Restaurant-related conversation (greetings, food
recommendations, asking about hours, payment methods) is NOT out-of-scope — use intent "conversation".
"""

MENU_READ_PROMPT = f"""MongoDB query for menu reads. {JSON_RULE}
Collection: menu — name(str lowercase), category, price(float), available(bool), description, prep_time(int)

show all menu:  {{"operation":"find","collection":"menu","filter":{{"available":true}},"sort":{{"category":1}}}}
biryani price:  {{"operation":"find","collection":"menu","filter":{{"name":"chicken biryani","available":true}}}}
starters:       {{"operation":"find","collection":"menu","filter":{{"category":"starter","available":true}}}}
drinks:         {{"operation":"find","collection":"menu","filter":{{"category":"drink","available":true}}}}

Always filter available:true unless user explicitly asks for unavailable.
If item not found in results, the system will show a professional "not available" message automatically.
"""

MENU_WRITE_PROMPT = f"""MongoDB query for menu management (staff). {JSON_RULE}
Collection: menu — name(lowercase), category, price, available(bool), description, prep_time

add item:   {{"operation":"update_one","collection":"menu","filter":{{"name":"mutton karahi"}},"update":{{"$set":{{"name":"mutton karahi","category":"main course","price":600,"available":true,"description":"Rich mutton karahi","prep_time":35}}}},"upsert":true}}
update price: {{"operation":"update_one","collection":"menu","filter":{{"name":"chicken biryani"}},"update":{{"$set":{{"price":400}}}}}}
disable:    {{"operation":"update_one","collection":"menu","filter":{{"name":"seekh kebab"}},"update":{{"$set":{{"available":false}}}}}}
enable:     {{"operation":"update_one","collection":"menu","filter":{{"name":"seekh kebab"}},"update":{{"$set":{{"available":true}}}}}}
"""

OFFERS_WRITE_PROMPT = f"""MongoDB query for offer management (staff). {JSON_RULE}
Collection: offers — title(str), description, discount_pct(float|null), deal_price(float|null), items(array of menu item names), active(bool), valid_until(str|null), created_at
{DATE_RULES}

CRITICAL: The "items" field must contain MENU ITEM NAMES (e.g. "chicken biryani", "raita") — NEVER the offer title.

add offer:
  {{"operation":"insert_one","collection":"offers","document":{{"title":"Friday Special","description":"Biryani ke saath Raita free","discount_pct":null,"deal_price":null,"items":["chicken biryani","raita"],"active":true,"valid_until":null,"created_at":"__TODAY_START__"}}}}

add % deal:
  {{"operation":"insert_one","collection":"offers","document":{{"title":"Weekend Deal","description":"20% off on all items","discount_pct":20,"deal_price":null,"items":["chicken biryani","beef karahi"],"active":true,"valid_until":null,"created_at":"__TODAY_START__"}}}}

disable offer by title (use $regex for partial/case-insensitive match):
  {{"operation":"update_one","collection":"offers","filter":{{"title":{{"$regex":"Friday","$options":"i"}}}},"update":{{"$set":{{"active":false}}}}}}

enable offer by title (use $regex for partial/case-insensitive match):
  {{"operation":"update_one","collection":"offers","filter":{{"title":{{"$regex":"Friday","$options":"i"}}}},"update":{{"$set":{{"active":true}}}}}}

update offer description/price:
  {{"operation":"update_one","collection":"offers","filter":{{"title":{{"$regex":"Weekend","$options":"i"}}}},"update":{{"$set":{{"discount_pct":30}}}}}}

RULES:
- For enable/disable: ALWAYS use {{"$regex":"<title_keyword>","$options":"i"}} filter — never exact string match
- Extract the key word(s) from offer title for regex (e.g. "friday deal disable" → regex "friday")
- items array = list of lowercase menu item names FROM THE MENU — never put the offer title here
- If staff doesn't specify items, use empty array []
- discount_pct and deal_price can both be null if not specified
- action "enable" → active:true, action "disable" → active:false
"""

ORDER_WRITE_PROMPT = f"""MongoDB query for order placement. {JSON_RULE}
Collections: orders, customers
{DATE_RULES}

Generate exactly:
{{
  "operations": [
    {{"operation":"insert_one","collection":"orders","document":{{
      "order_id":"<from context>","customer_name":"<lowercase>",
      "customer_phone":"<phone or null>","customer_address":"<address or null>",
      "items":[<from context>],"total_amount":<total>,
      "status":"received","payment_method":"<cash or from context>","payment_status":"pending",
      "notes":"<or null>","created_at":"__NOW__","updated_at":"__NOW__","status_updated_at":"__NOW__",
      "estimated_time":<eta>
    }}}},
    {{"operation":"update_one","collection":"customers","filter":{{"phone":"<phone>"}},
      "update":{{
        "$inc":{{"total_orders":1,"total_spent":<total>}},
        "$set":{{"last_order_at":"__NOW__","name":"<name>","address":"<address>"}},
        "$setOnInsert":{{"joined_at":"__NOW__"}}
      }},"upsert":true}}
  ]
}}
STRICT: DO NOT use ASCII-art, boxes, or lines (e.g. ||, ==, --) to draw a bill. Use simple Markdown lists and bold text ONLY.
"""

ORDER_READ_PROMPT = f"""MongoDB query for order tracking & staff status updates. {JSON_RULE}
Collection: orders
{DATE_RULES}
  __NOW__ = exact current UTC timestamp (use this for status_updated_at)

track by order ID:  {{"operation":"find","collection":"orders","filter":{{"order_id":"PKT-4F2A"}},"limit":1}}
track by phone:     {{"operation":"find","collection":"orders","filter":{{"customer_phone":"0300-1234567"}},"sort":{{"created_at":-1}},"limit":1}}
all active orders:  {{"operation":"find","collection":"orders","filter":{{"status":{{"$in":["received","preparing","ready","dispatched"]}}}},"sort":{{"created_at":1}}}}
update to dispatched (staff): {{"operation":"update_one","collection":"orders","filter":{{"order_id":"PKT-4F2A"}},"update":{{"$set":{{"status":"dispatched","updated_at":"__NOW__","status_updated_at":"__NOW__"}}}}}}
update to preparing (staff):  {{"operation":"update_one","collection":"orders","filter":{{"order_id":"PKT-4F2A"}},"update":{{"$set":{{"status":"preparing","updated_at":"__NOW__","status_updated_at":"__NOW__"}}}}}}
update to ready (staff):      {{"operation":"update_one","collection":"orders","filter":{{"order_id":"PKT-4F2A"}},"update":{{"$set":{{"status":"ready","updated_at":"__NOW__","status_updated_at":"__NOW__"}}}}}}
update to delivered (staff):  {{"operation":"update_one","collection":"orders","filter":{{"order_id":"PKT-4F2A"}},"update":{{"$set":{{"status":"delivered","updated_at":"__NOW__","status_updated_at":"__NOW__"}}}}}}

RULES:
- For track: always use find operation
- For status update: always use update_one with $set
- ALWAYS set both updated_at and status_updated_at to __NOW__ (NOT __TODAY_START__) in every status update
- __NOW__ gives exact current time — timers depend on this being accurate
"""

ANALYTICS_PROMPT = f"""MongoDB query for restaurant analytics & reports. {JSON_RULE}
Collection: orders — order_id, customer_name, customer_phone, items[], total_amount, status, payment_method, created_at, estimated_time
{DATE_RULES}

=== QUERY EXAMPLES BY ACTION ===

daily_report / today_summary (period=today):
  {{"operation":"aggregate","collection":"orders","pipeline":[
    {{"$match":{{"created_at":{{"$gte":"__TODAY_START__","$lte":"__TODAY_END__"}}}}}},
    {{"$group":{{"_id":null,"total_orders":{{"$sum":1}},"total_revenue":{{"$sum":"$total_amount"}},
      "cancelled":{{"$sum":{{"$cond":{{"if":{{"$eq":["$status","cancelled"]}},"then":1,"else":0}}}}}},
      "delivered":{{"$sum":{{"$cond":{{"if":{{"$eq":["$status","delivered"]}},"then":1,"else":0}}}}}},
      "avg_order":{{"$avg":"$total_amount"}}}}}}]}}

weekly_report (period=week):
  {{"operation":"aggregate","collection":"orders","pipeline":[
    {{"$match":{{"created_at":{{"$gte":"__WEEK_START__"}},"status":{{"$ne":"cancelled"}}}}}},
    {{"$group":{{"_id":null,"total_orders":{{"$sum":1}},"total_revenue":{{"$sum":"$total_amount"}},"avg_order":{{"$avg":"$total_amount"}}}}}}]}}

monthly_report (period=month):
  {{"operation":"aggregate","collection":"orders","pipeline":[
    {{"$match":{{"created_at":{{"$gte":"__MONTH_START__"}},"status":{{"$ne":"cancelled"}}}}}},
    {{"$group":{{"_id":null,"total_orders":{{"$sum":1}},"total_revenue":{{"$sum":"$total_amount"}},"avg_order":{{"$avg":"$total_amount"}}}}}}]}}

top_items (best sellers — CRITICAL: always include null-name filter after $unwind):
  MANDATORY field names: "_id" (item name), "qty" (quantity), "revenue" (sales amount). NEVER use other names.
  Week:
  {{"operation":"aggregate","collection":"orders","pipeline":[
    {{"$match":{{"created_at":{{"$gte":"__WEEK_START__"}},"status":{{"$ne":"cancelled"}}}}}},
    {{"$unwind":"$items"}},
    {{"$match":{{"items.name":{{"$type":"string","$ne":""}}}}}},
    {{"$group":{{"_id":"$items.name","qty":{{"$sum":"$items.qty"}},"revenue":{{"$sum":"$items.subtotal"}}}}}},
    {{"$match":{{"_id":{{"$ne":null}}}}}},
    {{"$sort":{{"qty":-1}}}},{{"$limit":10}}]}}
  Month:
  {{"operation":"aggregate","collection":"orders","pipeline":[
    {{"$match":{{"created_at":{{"$gte":"__MONTH_START__"}},"status":{{"$ne":"cancelled"}}}}}},
    {{"$unwind":"$items"}},
    {{"$match":{{"items.name":{{"$type":"string","$ne":""}}}}}},
    {{"$group":{{"_id":"$items.name","qty":{{"$sum":"$items.qty"}},"revenue":{{"$sum":"$items.subtotal"}}}}}},
    {{"$match":{{"_id":{{"$ne":null}}}}}},
    {{"$sort":{{"qty":-1}}}},{{"$limit":10}}]}}

top_customers (top customers by orders or spending):
  {{"operation":"find","collection":"customers","sort":{{"total_orders":-1}},"limit":10}}

all_orders / list_orders (aaj ke orders, all orders today with full detail):
  {{"operation":"find","collection":"orders",
    "filter":{{"created_at":{{"$gte":"__TODAY_START__","$lte":"__TODAY_END__"}}}},
    "sort":{{"created_at":-1}},"limit":50}}

all_orders_week (is hafte ke orders):
  {{"operation":"find","collection":"orders",
    "filter":{{"created_at":{{"$gte":"__WEEK_START__"}}}},
    "sort":{{"created_at":-1}},"limit":100}}

pending_orders:
  {{"operation":"find","collection":"orders",
    "filter":{{"status":{{"$in":["received","preparing","ready"]}}}},
    "sort":{{"created_at":1}}}}

order_detail (specific order by ID):
  {{"operation":"find","collection":"orders","filter":{{"order_id":"PKT-XXXX"}},"limit":1}}

revenue_summary / profit (period=today/week/month):
  Use daily_report aggregate for today, weekly for week, monthly for month.
  Note: profit estimation = revenue * 0.35 (35% margin assumption — no cost data in DB)

status_breakdown (how many in each status today):
  {{"operation":"aggregate","collection":"orders","pipeline":[
    {{"$match":{{"created_at":{{"$gte":"__TODAY_START__"}}}}}},
    {{"$group":{{"_id":"$status","count":{{"$sum":1}}}}}}]}}

RULES:
- ALWAYS use $cond object syntax: {{"$cond":{{"if":..., "then":..., "else":...}}}} — NEVER array form
- Always match action keyword to the closest example above
- For "daily"/"aaj" → TODAY_START/TODAY_END, "weekly"/"hafte" → WEEK_START, "monthly"/"mahine" → MONTH_START
- For top items: use the period requested (default: week)
- For "all orders today"/"aaj ke orders"/"orders ki detail" → use all_orders with today filter
- For "top customers"/"sabse zyada order dene wale" → use top_customers
- For profit/loss: use revenue aggregate; the LLM responder will calculate estimated profit
"""

CUSTOMER_PROMPT = f"""MongoDB query for customer lookup (staff only). {JSON_RULE}
Collections:
  customers — name, phone(PK), address, total_orders, total_spent, last_order_at
  orders    — order_id, customer_name, customer_phone, items[], total_amount, status, created_at
  feedback  — customer_name, customer_phone, message, rating(1-5), created_at

lookup by phone:          {{"operation":"find","collection":"customers","filter":{{"phone":"0300-1234567"}}}}
lookup by name:           {{"operation":"find","collection":"customers","filter":{{"name":{{"$regex":"asif","$options":"i"}}}},"limit":5}}
list_customers:           {{"operation":"find","collection":"customers","sort":{{"total_spent":-1}},"limit":20}}
top_customers:            {{"operation":"find","collection":"customers","sort":{{"total_orders":-1}},"limit":10}}
orders by phone:          {{"operation":"find","collection":"orders","filter":{{"customer_phone":"0300-1234567"}},"sort":{{"created_at":-1}},"limit":10}}
orders by name (REGEX):   {{"operation":"find","collection":"orders","filter":{{"customer_name":{{"$regex":"asif","$options":"i"}}}},"sort":{{"created_at":-1}},"limit":10}}
feedback (all):           {{"operation":"find","collection":"feedback","sort":{{"created_at":-1}},"limit":20}}
feedback (period):        {{"operation":"find","collection":"feedback","filter":{{"created_at":{{"$gte":"__MONTH_START__"}}}},"sort":{{"created_at":-1}},"limit":20}}

RULES:
- Action "feedback" → query feedback collection (use date filter if period mentioned)
- Action "customer_orders" AND phone given → filter orders by customer_phone
- Action "customer_orders" AND name given BUT no phone → filter orders by customer_name using $regex
- Action "list_customers" OR (no phone AND no name) → list customers sorted by total_spent
- Action "top_customers" → sort customers by total_orders descending
- Name search: ALWAYS use {{"$regex":"<name>","$options":"i"}} — never exact string match
- For orders by name: search orders collection with customer_name regex (NOT customers collection)
- Use __MONTH_START__ / __WEEK_START__ / __TODAY_START__ for date filters when period is mentioned
"""

RESPONDER_PROMPT = """
You are PakOrderBot — a friendly, natural assistant at a Pakistani restaurant.
Respond in Roman Urdu mixed with English. Sound like a real person, not a formal robot.

LANGUAGE STYLE — vary your responses naturally:
- DO NOT start every sentence with "janab" or "meherbani" — use them at most ONCE per reply
- DO NOT repeat filler words: zaroor, bilkul, shukriya — use them occasionally, not every line
- Sound conversational: "Acha! 2 chicken biryani — perfect choice." NOT "Meherbani, zaroor aapka shukriya."
- Mix Urdu + English naturally: "Order aa gaya!", "Total Rs 400 hai", "35 minutes mein ready ho jaye ga"
- Vary openers: Acha! / Bilkul! / Theek hai! / Sure! / Done! / Got it! / Zaroor!
- For refusals: be brief and redirect — don't lecture

BANNED PHRASES (never use these):
- "meherbani se" at the start of every sentence
- "zaroor apni requirements bataen"
- "hum apko assist karne ke liye tayar hain"
- "jaankari nahi" / "uplabdh nahi" / "afsoos" / "maafi chahta hoon"
- Any robotic corporate-speak

SCOPE — what PakOrderBot can help with:
  ✅ Menu items, prices, availability
  ✅ Placing, tracking, modifying, cancelling orders
  ✅ Deals and offers
  ✅ Food recommendations
  ✅ Restaurant general questions (timings, location, payment methods)
  ✅ Submitting feedback

OUT-OF-SCOPE RULE (VERY IMPORTANT):
If the user asks about ANYTHING outside the above list — e.g. politics, weather, sports, coding,
general knowledge, news, other businesses, math, medical advice, jokes, creative writing, etc. —
respond with a short, warm, professional refusal in Roman Urdu, then redirect to restaurant services.

Example out-of-scope responses (vary them, never repeat the same one):
  "Yeh meri expertise nahi — main sirf restaurant ke baare mein help kar sakta hoon! 😊 Menu dekhna hai ya kuch order karna hai?"
  "Main ek restaurant assistant hoon — in cheezon mein help nahi kar sakta. Koi order karna ho ya menu check karna ho? 🍛"
  "Is topic par main kuch nahi bata sakta. Lekin agar khane peene ka koi sawaal ho — zaroor bataiye! 😊"

DB-EMPTY / NOT FOUND RULE:
If DB result is empty or shows no data found, respond naturally — e.g.:
  "Is order ID se koi order nahi mila. Order ID check karein (e.g. PKT-XXXX)."
  "Abhi koi active orders nahi hain."
  "Yeh item menu mein nahi hai — 'menu dikhao' likh kar available items dekhein."
Never say "try again later" or "system error" unless there's an actual ERROR: prefix in results.

STRICT RULES:
- ONLY use data from DB result — never invent prices, order IDs, or times
- NEVER ask for info already given — check conversation history
- Keep replies SHORT — 1-3 sentences for simple things, no padding
- If DB result is empty, say so simply without filler phrases

STATUS EMOJI: received=📥 preparing=👨‍🍳 ready=✅ dispatched=🚗 delivered=✓ cancelled=❌
"""

STAFF_RESPONDER_PROMPT = """
You are PakOrderBot — the AI assistant for restaurant STAFF.
Respond in Roman Urdu + English. Be concise and professional.

STAFF RESPONSE RULES:
- Display data in clean tables or bullet lists
- Show all numbers: orders count, revenue, profit clearly
- For reports: show summary first, then details
- For order lists: show order ID, customer, total, status, items
- For menu operations: confirm exactly what was changed
- Keep it business-focused — no fluff

SCOPE — what staff can ask about:
  ✅ Sales reports (daily/weekly/monthly)
  ✅ Order management and status updates
  ✅ Menu add/edit/disable
  ✅ Offer/deal management
  ✅ Customer records and feedback
  ✅ Top items, top customers, analytics

OUT-OF-SCOPE RULE (VERY IMPORTANT):
If staff asks about ANYTHING outside restaurant operations — e.g. general knowledge, news,
coding help, politics, math, personal advice, other topics — respond with a short professional
refusal and redirect.

Example out-of-scope responses:
  "Main sirf restaurant operations mein help kar sakta hoon. Koi report, menu update, ya order query ho to bataiye!"
  "Is topic par help nahi kar sakta. Sales report, orders, ya menu ke baare mein kuch chahiye?"

DB-EMPTY / DATA NOT FOUND:
- If data is empty: say clearly what period/query returned nothing, e.g. "Aaj koi order nahi aaya." or "Koi customer record nahi mila."
- If query failed: say "Query execute nahi ho saki — dobara try karein."
- NEVER say generic "try again later" for empty results — be specific about what's missing.

FORMAT: Use monospace-style alignment where helpful. Be direct.
"""

CART_DECISION_PROMPT = f"""
You are a smart cart manager for PakOrderBot — a Pakistani restaurant chatbot.
{JSON_RULE}

The customer has a pending cart. Decide what they want:
1. They want to ADD or REMOVE items → action: "modified", return full updated items list
2. They want to PROCEED / are done → action: "done"
3. They are saying YES to the question "koi aur cheez chahiye?" but havent named items yet → action: "ask_what"

OUTPUT for modified:
{{"action":"modified","items":[{{"name":"<lowercase>","qty":<int>}}]}}

OUTPUT for done (no more items, proceed to checkout):
{{"action":"done"}}

OUTPUT for ask_what (said yes/haan but no item specified):
{{"action":"ask_what"}}

DONE signals — any of these mean the customer is done adding:
  nahi, na, no, nope, nhi, bas, theek hai, done, kuch nahi, bus, nahi chahiye,
  order book kar do, book kar do, order karo, confirm karo, aage chalo, proceed,
  order place karo, book it, thik hai, ho gaya, yahi chahiye, bas yahi, enough

ADD signals — customer names a specific item or quantity:
  "1 ice cream add karo", "aur 2 naan chahiye", "raita bhi lena hai"

YES-BUT-NO-ITEM signals — said haan/yes/ok without naming anything:
  "haan", "yes", "ok", "ji", "bilkul", "zaroor", "haan chahiye"

RULES:
- item names must be lowercase
- Return COMPLETE updated list (existing + new), not just changes
- If removing: decrease qty or remove item entirely
- NEVER return action "modified" unless a specific item name is mentioned
"""


def _staff_orders_display(orders: list) -> str:
    """Format a list of orders for staff chatbot display."""
    if not orders:
        return "📭 Koi order nahi mila."
    STATUS_EM = {"received":"📥","preparing":"👨‍🍳","ready":"✅","dispatched":"🚗","delivered":"✓","cancelled":"❌"}
    lines = [f"### 📋 Orders ({len(orders)} total)\n---"]
    for o in orders[:20]:
        oid    = o.get("order_id","?")
        name   = (o.get("customer_name") or "Mehman").title()
        phone  = o.get("customer_phone","—") or "—"
        total  = o.get("total_amount",0)
        status = o.get("status","received")
        sem    = STATUS_EM.get(status,"")
        items  = ", ".join(f"{i.get('qty',1)}x {i.get('name','').title()}" for i in o.get("items",[]))
        created = o.get("created_at","")
        ts = created.strftime("%H:%M") if hasattr(created,"strftime") else str(created)[:16] if created else ""
        lines.append(f"#### {sem} `#{oid}` — {name}")
        lines.append(f"- **Total**: Rs {total:,.0f} `[{status.upper()}]`")
        lines.append(f"- **Phone**: {phone}")
        lines.append(f"- **Items**: {items}")
        if ts: lines.append(f"- **Time**: {ts}")
        lines.append("---")
    if len(orders) > 20:
        lines.append(f"*... aur {len(orders)-20} orders (staff panel mein poora dekho)*")
    return "\n".join(lines)


def _staff_analytics_display(data: dict, user_msg: str = "") -> str:
    """Format analytics/report result for staff. Never returns '' — always returns a string."""
    msg_low = user_msg.lower()

    # ── Normalise: executor sends "data" OR "results" key ────────────────────
    rows_raw = data.get("data") or data.get("results") or []
    if not isinstance(rows_raw, list):
        rows_raw = []

    # ── Guard: empty data ─────────────────────────────────────────────────────
    if not rows_raw:
        return ""   # caller will handle EMPTY separately

    first = rows_raw[0] if rows_raw else {}

    # ── Guard: if data looks like customer records (has "name" + "total_orders" but no "_id") ──
    # These should go through _staff_customer_display, not here
    if "name" in first and "total_orders" in first and "_id" not in first:
        return ""   # signal caller to use customer display instead

    # ── TOP ITEMS: has _id (item name) + qty + revenue ──────────────────────
    # Normalize: LLM may use qty/total_qty and revenue/rev
    qty_key = next((k for k in ("qty","total_qty","total_sold") if k in first), None)
    rev_key = next((k for k in ("revenue","rev","total_revenue") if k in first), None)
    if qty_key and "_id" in first and "total_orders" not in first and "count" not in first:
        # Filter rows with valid string name
        valid_rows = [
            row for row in rows_raw
            if row.get("_id") and isinstance(row["_id"], str) and row["_id"].strip()
        ]
        if not valid_rows:
            return "📭 Top items data mein item names nahi mile. Orders ka data check karein."
        MEDALS = ["🥇","🥈","🥉","4.","5.","6.","7.","8.","9.","10."]
        lines = [
            "### 🏆 TOP SELLING ITEMS",
            "| Rank | Item Name | Qty | Revenue |",
            "|---|---|---|---|"
        ]
        for i, row in enumerate(valid_rows[:10]):
            name  = row["_id"].title()
            qty   = row.get(qty_key, 0) or 0
            rev   = row.get(rev_key, 0) if rev_key else 0
            medal = MEDALS[i] if i < len(MEDALS) else f"{i+1}."
            lines.append(f"| {medal} | **{name}** | {qty} pcs | Rs {rev:,.0f} |")
        return "\n".join(lines)

    # ── STATUS BREAKDOWN: has _id (status string) + count field ──────────────
    if "count" in first and "_id" in first and "total_orders" not in first:
        STATUS_EM = {"received":"📥","preparing":"👨‍🍳","ready":"✅","dispatched":"🚗","delivered":"✓","cancelled":"❌"}
        lines = ["### 📊 STATUS BREAKDOWN\n---"]
        for row in rows_raw:
            s = str(row.get("_id") or "?")
            c = row.get("count", 0)
            lines.append(f"- {STATUS_EM.get(s,'')} **{s.upper()}**: {c} orders")
        return "\n".join(lines)

    # ── AGGREGATE SUMMARY: total_orders / total_revenue ──────────────────────
    if "total_revenue" in first or "total_orders" in first:
        total_rev  = first.get("total_revenue", 0) or 0
        total_ord  = first.get("total_orders",  0) or 0
        avg_ord    = first.get("avg_order", round(total_rev / total_ord, 2) if total_ord else 0)
        cancelled  = first.get("cancelled",  0) or 0
        delivered  = first.get("delivered",  0) or 0
        est_profit = round(total_rev * 0.35, 0)

        # Period label — covers Roman Urdu variants
        if any(w in msg_low for w in ("today","aaj","aj","din")):
            period = "AJ"
        elif any(w in msg_low for w in ("week","hafte","hafta","weekly")):
            period = "IS HAFTE"
        elif any(w in msg_low for w in ("month","mahine","mahina","maheene","monthly")):
            period = "IS MAHINE"
        else:
            period = "PERIOD"

        lines = [
            f"### 📊 {period} KI SALES REPORT",
            "---",
            f"- 📦 **Total Orders**      : {total_ord}",
            f"- 💰 **Total Revenue**     : Rs {total_rev:,.0f}",
            f"- 📈 **Avg Order Value**   : Rs {avg_ord:,.0f}",
            f"- 💵 **Est. Profit (35%)** : Rs {est_profit:,.0f}",
        ]
        if cancelled:
            lines.append(f"- ❌ **Cancelled**         : {cancelled}")
        if delivered:
            lines.append(f"- ✓  **Delivered**         : {delivered}")
        if total_ord == 0:
            lines.append("\n*ℹ️ Is period mein koi order nahi aaya.*")
        return "\n".join(lines)

    return ""


def _staff_customer_display(data: list, title: str = "CUSTOMER INFO") -> str:
    """Format customer records for staff."""
    if not data:
        return "👤 Koi customer record nahi mila."
    lines = [f"### 👤 {title} ({len(data)} records)\n---"]
    for i, c in enumerate(data[:20], 1):
        name    = (c.get("name") or "—").title()
        phone   = c.get("phone","—") or "—"
        addr    = (c.get("address") or "—")
        orders  = c.get("total_orders", 0) or 0
        spent   = c.get("total_spent", 0) or 0
        last    = c.get("last_order_at","")
        last_ts = last.strftime("%d %b %Y") if hasattr(last,"strftime") else str(last)[:10] if last else "—"
        lines += [
            f"#### {i}. 👤 {name}",
            f"- 📱 **Phone**: {phone}",
            f"- 📍 **Address**: {addr[:50]}",
            f"- 📦 **Orders**: {orders} | 💰 **Total**: Rs {spent:,.0f} | 🕐 **Last**: {last_ts}",
            "---",
        ]
    return "\n".join(lines)


def _staff_feedback_display(data: list) -> str:
    """Format customer feedback for staff using clean Markdown."""
    if not data:
        return "💬 Abhi tak koi customer feedback nahi mila."
    
    lines = [f"### 💬 Customer Feedback ({len(data)} total)\n---"]
    for fb in data[:20]:
        name   = (fb.get("customer_name") or fb.get("name") or "Anonymous").title()
        phone  = fb.get("customer_phone") or fb.get("phone") or "—"
        msg    = (fb.get("message") or fb.get("comment") or
                  fb.get("text") or fb.get("feedback") or "").strip()
        rating = fb.get("rating", 0)
        stars  = ("⭐" * int(rating)) if rating else "☆☆☆☆☆"
        created = fb.get("created_at","")
        ts = created.strftime("%d %b %Y") if hasattr(created,"strftime") else str(created)[:10] if created else "—"
        
        lines += [
            f"#### {stars} — {name}",
            f"- 📱 **Phone**: {phone}",
            f"- 💬 **Message**: {msg if msg else '*(No text message)*'}",
            f"- 📅 **Date**: {ts}",
            "---"
        ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  NODE 1: ROUTER
# ─────────────────────────────────────────────────────────────────────────────

async def router_node(state: AgentState) -> dict:
    user_msg    = state["user_message"].strip()
    history     = state.get("conversation_history") or []
    user_role   = state.get("user_role", "customer")
    conv_stage  = state.get("conv_stage", "")
    order_draft = state.get("order_draft") or {}

    # ── await_more: one smart LLM call decides done vs add/remove ──────────
    if conv_stage == "await_more":
        cart_items = order_draft.get("items", [])
        cart_json  = json.dumps([{"name":i["name"],"qty":i["qty"]} for i in cart_items])
        try:
            r = await groq_client.chat.completions.create(
                messages=[
                    {"role":"system","content":CART_DECISION_PROMPT},
                    {"role":"user","content":f"Current cart: {cart_json}\nCustomer said: {user_msg}"}
                ],
                model=MODEL, response_format={"type":"json_object"}, temperature=0.0)
            decision = json.loads(r.choices[0].message.content)
        except Exception:
            decision = {"action":"done"}  # safe fallback

        cart_action = decision.get("action","done")

        if cart_action == "ask_what":
            # Said yes/haan but no item — ask what they want
            return {**state,
                    "tasks":[{"intent":"conversation","action":"ask_what_to_add"}],
                    "intent":"conversation","action":"ask_what_to_add",
                    "conv_stage":"await_more","order_draft":order_draft}

        elif cart_action == "modified" and decision.get("items"):
            # Items to add/remove — re-enrich and update draft
            return {**state,
                    "tasks":[{"intent":"conversation","action":"apply_modification",
                              "_new_items": decision.get("items",[])}],
                    "intent":"conversation","action":"apply_modification",
                    "conv_stage":"await_more","order_draft":order_draft}

        else:
            # Done — move to personal info
            return {**state,
                    "tasks":[{"intent":"conversation","action":"collect_name"}],
                    "intent":"conversation","action":"collect_name",
                    "conv_stage":"await_name","order_draft":order_draft}

    # ── Personal info collection ─────────────────────────────────────────────
    if conv_stage == "await_name":
        order_draft["customer_name"] = user_msg.strip().lower()
        return {**state, "tasks":[{"intent":"conversation","action":"collect_phone"}],
                "intent":"conversation","action":"collect_phone",
                "conv_stage":"await_phone","order_draft":order_draft}

    if conv_stage == "await_phone":
        order_draft["customer_phone"] = user_msg.strip()
        return {**state, "tasks":[{"intent":"conversation","action":"collect_address"}],
                "intent":"conversation","action":"collect_address",
                "conv_stage":"await_address","order_draft":order_draft}

    if conv_stage == "await_address":
        order_draft["customer_address"] = user_msg.strip()
        return {**state, "tasks":[{"intent":"conversation","action":"show_bill"}],
                "intent":"conversation","action":"show_bill",
                "conv_stage":"await_confirm","order_draft":order_draft}

    if conv_stage == "await_confirm":
        yes = user_msg.lower() in ("yes","haan","ha","han","confirm","ok","okay","ji","bilkul","zaroor","y","ha ji","haan ji")
        if yes:
            task = {
                "intent":         "order_place",
                "action":         "confirm_order",
                "_use_draft":     True,
                "_order_id":      order_draft.get("order_id"),
                "_enriched_items":order_draft.get("items",[]),
                "_total":         order_draft.get("total",0),
                "_eta":           order_draft.get("eta",30),
                "_unavailable":   order_draft.get("unavailable",[]),
                "customer_name":  order_draft.get("customer_name","mehman"),
                "customer_phone": order_draft.get("customer_phone"),
                "customer_address":order_draft.get("customer_address"),
                "payment_method": order_draft.get("payment_method","cash"),
                "notes":          order_draft.get("notes"),
                "items":          order_draft.get("items",[]),
            }
            return {**state, "tasks":[task],"intent":"order_place","action":"confirm_order",
                    "conv_stage":"confirmed","order_draft":order_draft}
        else:
            return {**state, "tasks":[{"intent":"conversation","action":"order_cancelled_by_user"}],
                    "intent":"conversation","action":"order_cancelled_by_user",
                    "conv_stage":"","order_draft":{}}

    # ── Hard keyword guard — ONLY for customers, skip entirely for staff ───────
    if user_role != "staff":
        import re as _re
        CUSTOMER_BLOCKED_PATTERNS = [
            # menu editing
            r"menu.{0,20}(add|daal|daalo|update|badlo|change|edit|hatao|remove|delete)",
            r"(add|daal|daalo).{0,20}menu",
            r"naya.{0,10}(item|dish|cheez).{0,15}(add|daal)",
            r"price.{0,15}(change|badlo|update)",
            # other customers' data / orders
            r"(baki|doosre|sab|all).{0,15}(customer|order)",
            r"(kisi|kisi bhi).{0,10}(customer|order).{0,15}(data|info|dekhao|batao|dikhao)",
            r"(customer|orders).{0,15}list",
            r"(kitne|sab).{0,10}order.{0,10}(aaye|hain|hai)",
            # analytics / reports / profit
            r"(revenue|income|kamai|total sales|daily report|analytics|stats)",
            r"(aaj|week|month).{0,10}(kitna|total|income|sales|revenue)",
            r"(profit|loss|munafa|nuqsan)",
            r"(report|summary|breakdown).{0,20}(banao|dikhao|chahiye)",
            r"top.{0,10}(item|product|dish|seller)",
            r"best.{0,10}(seller|item|product|bikne wala)",
            # offer management
            r"(offer|deal).{0,15}(add|daal|update|delete|hatao|change)",
        ]
        msg_lower = user_msg.lower()
        for pattern in CUSTOMER_BLOCKED_PATTERNS:
            if _re.search(pattern, msg_lower):
                blocked_task = {"intent":"conversation","action":"access_denied_customer","items":[]}
                return {**state, "tasks":[blocked_task],
                        "intent":"conversation","action":"access_denied_customer",
                        "entities":blocked_task,"extracted_intent":{"tasks":[blocked_task]},
                        "user_role":user_role}

    # ── Normal LLM routing ────────────────────────────────────────────────────
    prior = history[-8:]   # use last 8 turns for context

    # ── Fetch real-time menu context from DB ──────────────────────────────────
    menu_context = await _get_menu_context()

    # For staff: prepend a role-context note so LLM classifies correctly
    staff_note = ""
    if user_role == "staff":
        staff_note = (
            "\n\n[STAFF MODE] This request is from an authenticated restaurant staff member. "
            "They CAN access: analytics, all orders, customer data, menu management, offers. "
            "Route accordingly — do NOT use access_denied_customer action ever for staff."
        )

    msgs  = [{"role":"system","content":ROUTER_PROMPT + f"\n\nCURRENT MENU CONTEXT:\n{menu_context}" + staff_note}]
    for h in prior:
        msgs.append({"role":h["role"],"content":h["content"]})
    msgs.append({"role":"user","content":user_msg})

    res = await groq_client.chat.completions.create(
        messages=msgs, model=MODEL, response_format={"type":"json_object"}, temperature=0.0)
    try:
        out   = json.loads(res.choices[0].message.content)
        tasks = out.get("tasks", [])
    except Exception:
        tasks = [{"intent":"conversation","action":"fallback"}]; out = {}

    valid = {"menu_read","offers_read","popular_items","order_place","order_modify","order_track","order_cancel",
             "feedback_write","menu_write","offers_write","order_update","analytics_read","customer_read","conversation"}
    for t in tasks:
        if t.get("intent") not in valid: t["intent"] = "conversation"
        # Post-LLM guard: block staff intents for non-staff ONLY
        if user_role != "staff" and t.get("intent") in {"menu_write","offers_write","order_update","analytics_read","customer_read"}:
            t["intent"] = "conversation"
            t["action"] = "access_denied_customer"
        if not isinstance(t.get("items"),list): t["items"] = []
        for it in t.get("items",[]):
            if it.get("name"): it["name"] = it["name"].lower().strip()

    return {**state, "tasks":tasks,
            "intent":tasks[0].get("intent","conversation"),
            "action":tasks[0].get("action",""),
            "entities":tasks[0], "extracted_intent":out,
            "user_role":user_role}


# ─────────────────────────────────────────────────────────────────────────────
#  NODE 2: QUERY BUILDER
# ─────────────────────────────────────────────────────────────────────────────

async def _build_plan(task, ctx, user_role):
    intent = task.get("intent","")

    if intent in STAFF_ONLY and user_role != "staff":
        return {"operation":"access_denied"}
    # Extra guard: customer asking for analytics/customer_read even if somehow not caught above
    if user_role != "staff" and intent in {"analytics_read","customer_read","menu_write","offers_write","order_update"}:
        return {"operation":"access_denied"}
    # order_cancel is always allowed for customers

    if intent == "popular_items":
        # Direct pipeline — null-safe item name grouping
        return {
            "operation": "aggregate",
            "collection": "orders",
            "pipeline": [
                {"$match": {"status": {"$ne": "cancelled"}}},
                {"$unwind": "$items"},
                {"$match": {"items.name": {"$type": "string", "$ne": ""}}},
                {"$group": {
                    "_id":     "$items.name",
                    "qty":     {"$sum": "$items.qty"},
                    "revenue": {"$sum": "$items.subtotal"}
                }},
                {"$match": {"_id": {"$ne": None}}},
                {"$sort": {"qty": -1}},
                {"$limit": 5}
            ]
        }

    if intent == "menu_read":
        # ── Fetch real-time menu context for Query Builder ────────────────────
        menu_context = await _get_menu_context()
        r = await groq_client.chat.completions.create(
            messages=[{"role":"system","content":MENU_READ_PROMPT + f"\n\nKNOWN MENU ITEMS:\n{menu_context}"},
                      {"role":"user","content":f"User: {ctx}\nAction: {task.get('action','')}"}],
            model=MODEL, response_format={"type":"json_object"}, temperature=0.0)
        try: return json.loads(r.choices[0].message.content)
        except: return {"operation":"unsupported"}

    elif intent == "offers_read":
        # Direct query — no LLM hallucination possible
        return {"operation":"find","collection":"offers","filter":{"active":True}}

    elif intent == "menu_write":
        mi = task.get("menu_item") or {}
        r = await groq_client.chat.completions.create(
            messages=[{"role":"system","content":MENU_WRITE_PROMPT},
                      {"role":"user","content":f"Action:{task.get('action','')}\nItem:{json.dumps(mi)}\nUser:{ctx}"}],
            model=MODEL, response_format={"type":"json_object"}, temperature=0.0)
        try: return json.loads(r.choices[0].message.content)
        except: return {"operation":"unsupported"}

    elif intent == "offers_write":
        oi = task.get("offer_item") or {}
        r = await groq_client.chat.completions.create(
            messages=[{"role":"system","content":OFFERS_WRITE_PROMPT},
                      {"role":"user","content":f"Action:{task.get('action','')}\nOffer:{json.dumps(oi)}\nUser:{ctx}"}],
            model=MODEL, response_format={"type":"json_object"}, temperature=0.0)
        try: return json.loads(r.choices[0].message.content)
        except: return {"operation":"unsupported"}

    elif intent == "order_place":
        # ── confirm_order: draft already enriched, build plan directly ───────
        if task.get("_use_draft"):
            enriched = task.get("_enriched_items", [])
            total    = task.get("_total", 0)
            eta      = task.get("_eta", 30)
            oid      = task.get("_order_id") or _oid()
            task["_order_id"]       = oid
            task["_enriched_items"] = enriched
            task["_total"]          = total
            task["_eta"]            = eta
            task["_unavailable"]    = task.get("_unavailable", [])
            c2 = (f"Place order.\norder_id:{oid}\n"
                  f"customer_name:{task.get('customer_name','mehman')}\n"
                  f"customer_phone:{task.get('customer_phone') or 'null'}\n"
                  f"customer_address:{task.get('customer_address') or 'null'}\n"
                  f"items:{json.dumps(enriched)}\ntotal_amount:{total}\n"
                  f"payment_method:{task.get('payment_method') or 'cash'}\n"
                  f"notes:{task.get('notes') or 'null'}\nestimated_time:{eta}")
            r = await groq_client.chat.completions.create(
                messages=[{"role":"system","content":ORDER_WRITE_PROMPT},
                          {"role":"user","content":c2}],
                model=MODEL, response_format={"type":"json_object"}, temperature=0.0)
            try:    return json.loads(r.choices[0].message.content)
            except: return {"operation":"unsupported"}

        # ── New order: enrich items first ─────────────────────────────────────
        items = task.get("items", [])
        if not items: return {"operation": "no_items"}
        enriched, total, prep_time, delivery_time, unavail = await _enrich(items)
        eta = prep_time + delivery_time
        if unavail and not enriched:
            return {"operation": "items_unavailable", "items": unavail}
        oid = _oid()
        task["_order_id"]=oid; task["_enriched_items"]=enriched
        task["_total"]=total;  task["_eta"]=eta
        task["_prep_time"]=prep_time; task["_delivery_time"]=delivery_time
        task["_unavailable"]=unavail

        if task.get("customer_name") and task.get("customer_phone") and task.get("customer_address"):
            c2 = (f"Place order.\norder_id:{oid}\n"
                  f"customer_name:{task.get('customer_name','mehman')}\n"
                  f"customer_phone:{task.get('customer_phone')}\n"
                  f"customer_address:{task.get('customer_address')}\n"
                  f"items:{json.dumps(enriched)}\ntotal_amount:{total}\n"
                  f"payment_method:{task.get('payment_method') or 'cash'}\n"
                  f"notes:{task.get('notes') or 'null'}\nestimated_time:{eta}")
            r = await groq_client.chat.completions.create(
                messages=[{"role":"system","content":ORDER_WRITE_PROMPT},
                          {"role":"user","content":c2}],
                model=MODEL, response_format={"type":"json_object"}, temperature=0.0)
            try:    return json.loads(r.choices[0].message.content)
            except: return {"operation":"unsupported"}

        return {"operation": "need_customer_info"}
    elif intent == "order_cancel":
        # Direct plan — no LLM, no crash risk
        oid   = task.get("order_id")
        phone = task.get("customer_phone")
        if oid:
            filt = {"order_id": oid}
        elif phone:
            filt = {"customer_phone": phone}
        else:
            return {"operation": "unsupported"}
        return {
            "operation": "update_one",
            "collection": "orders",
            "filter": filt,
            "update": {"$set": {"status": "cancelled", "updated_at": "__TODAY_START__"}}
        }

    elif intent == "order_modify":
        # Fetch existing order from DB, merge items, update — all in Python
        # Return a special signal; executor handles the fetch+merge+update
        oid   = task.get("order_id")
        phone = task.get("customer_phone")
        if not oid and not phone:
            return {"operation": "unsupported"}
        return {
            "operation":   "order_modify",
            "order_id":    oid,
            "phone":       phone,
            "add_items":   task.get("items", []),    # items to add (with qty)
            "remove_items":task.get("remove_items", []),  # items to remove
        }

    elif intent in ("order_track", "order_update"):
        c2 = (f"Action:{task.get('action','')}\norder_id:{task.get('order_id') or 'null'}\n"
              f"customer_phone:{task.get('customer_phone') or 'null'}\nnew_status:{task.get('new_status') or 'null'}")
        r = await groq_client.chat.completions.create(
            messages=[{"role":"system","content":ORDER_READ_PROMPT},{"role":"user","content":c2}],
            model=MODEL, response_format={"type":"json_object"}, temperature=0.0)
        try: return json.loads(r.choices[0].message.content)
        except: return {"operation":"unsupported"}

    elif intent == "customer_read":
        action_str = task.get("action","").lower()
        name_str   = task.get("customer_name") or ""
        phone_str  = task.get("customer_phone") or ""

        # ── Direct plans (no LLM needed) ─────────────────────────────────────
        # Top customers
        if action_str in ("top_customers","top_customer"):
            return {"operation":"find","collection":"customers",
                    "sort":{"total_orders":-1},"limit":10}

        # Feedback
        if action_str == "feedback":
            return {"operation":"find","collection":"feedback",
                    "sort":{"created_at":-1},"limit":30}

        # Order history by phone
        if action_str == "customer_orders" and phone_str:
            return {"operation":"find","collection":"orders",
                    "filter":{"customer_phone": phone_str},
                    "sort":{"created_at":-1},"limit":15}

        # Order history by name (no phone) — search orders collection with name regex
        if action_str == "customer_orders" and name_str and not phone_str:
            return {"operation":"find","collection":"orders",
                    "filter":{"customer_name":{"$regex": name_str, "$options":"i"}},
                    "sort":{"created_at":-1},"limit":15}

        # List all customers (or name-based lookup if name given)
        if action_str == "list_customers" or (not phone_str and not name_str):
            if name_str:
                # Name given → search customers collection by name
                return {"operation":"find","collection":"customers",
                        "filter":{"name":{"$regex": name_str, "$options":"i"}},
                        "limit":5}
            return {"operation":"find","collection":"customers",
                    "sort":{"total_spent":-1},"limit":20}

        # Fallback: name/phone lookup via LLM
        c2 = f"Action:{action_str}\nphone:{phone_str or 'null'}\nname:{name_str or 'null'}\noriginal_query:{ctx}"
        r = await groq_client.chat.completions.create(
            messages=[{"role":"system","content":CUSTOMER_PROMPT},{"role":"user","content":c2}],
            model=MODEL, response_format={"type":"json_object"}, temperature=0.0)
        try: return json.loads(r.choices[0].message.content)
        except: return {"operation":"unsupported"}

    elif intent == "analytics_read":
        action_str = task.get("action","")
        period_str = task.get("period") or "today"
        ctx_low = ctx.lower()

        # ── Infer period from context if LLM missed it ────────────────────────
        MONTH_WORDS = ("month","mahine","mahina","maheene","monthly","mahiny")
        WEEK_WORDS  = ("week","hafte","hafta","weekly","is hafte","hafte mein")
        TODAY_WORDS = ("today","aaj","aj ","aj ke","aj ki","aaj ki","aaj ke","din ki","din ke")
        if any(w in ctx_low for w in MONTH_WORDS):
            period_str = "month"
        elif any(w in ctx_low for w in WEEK_WORDS):
            period_str = "week"
        elif any(w in ctx_low for w in TODAY_WORDS):
            period_str = "today"

        # ── Infer action if LLM returned empty/wrong ─────────────────────────
        if not action_str:
            SALE_WORDS = ("sale","sales","kamai","revenue","bikri","income","report","hisaab","kitna","kite")
            if any(w in ctx_low for w in SALE_WORDS):
                action_str = "daily_report" if period_str == "today" else \
                             "weekly_report" if period_str == "week" else "monthly_report"
            elif any(w in ctx_low for w in ("top item","op item","best seller","zyada bika","popular")):
                action_str = "top_items"
            elif any(w in ctx_low for w in ("order","orders")):
                action_str = "all_orders"

        # ── top_customers: direct plan, no LLM ───────────────────────────────
        if action_str == "top_customers" or any(w in ctx_low for w in
                ("top customer","sabse zyada order dene","best customer","top client","loyal customer")):
            return {"operation":"find","collection":"customers",
                    "sort":{"total_orders":-1},"limit":10}

        c2 = f"Action:{action_str}\nPeriod:{period_str}\nUser query:{ctx}"
        r = await groq_client.chat.completions.create(
            messages=[{"role":"system","content":ANALYTICS_PROMPT},{"role":"user","content":c2}],
            model=MODEL, response_format={"type":"json_object"}, temperature=0.0)
        try: return json.loads(r.choices[0].message.content)
        except: return {"operation":"unsupported"}

    elif intent == "feedback_write":
        # Customer submits feedback — insert into feedback collection
        message = task.get("feedback_message") or task.get("notes") or ""
        rating  = task.get("feedback_rating")
        name    = task.get("customer_name") or "mehman"
        phone   = task.get("customer_phone") or ""
        if not message:
            return {"operation": "no_feedback"}
        doc = {
            "customer_name":  name,
            "customer_phone": phone,
            "message":        message,
            "rating":         rating,
            "created_at":     "__TODAY_START__"
        }
        return {"operation": "insert_one", "collection": "feedback", "document": doc}

    return {"operation":"conversation"}


async def query_builder_node(state: AgentState) -> dict:
    tasks     = state.get("tasks",[])
    user_msg  = state["user_message"]
    history   = state.get("conversation_history") or []
    user_role = state.get("user_role","customer")
    conv_stage= state.get("conv_stage","")
    order_draft = state.get("order_draft") or {}

    PASS = {"collect_phone","collect_address","collect_name","show_bill",
            "order_cancelled_by_user","apply_modification","ask_what_to_add"}
    if tasks and tasks[0].get("action") in PASS:
        return {**state, "query_plan":{"operation":"conversation"},
                "all_plans":[{"intent":"conversation","action":tasks[0].get("action"),
                               "plan":{"operation":"conversation"},"task":tasks[0]}]}
    if not tasks:
        return {**state,"query_plan":{"operation":"unsupported"},"all_plans":[]}

    prior = history[-8:]
    ctx   = ("\n".join(f"{'User' if h['role']=='user' else 'Bot'}:{h['content']}" for h in prior)
             + f"\nCurrent:{user_msg}") if prior else user_msg

    plans  = await asyncio.gather(*[_build_plan(t, ctx, user_role) for t in tasks])
    tagged = [{"intent":t.get("intent",""),"action":t.get("action",""),"plan":p,"task":t}
              for t,p in zip(tasks,plans)]
    return {**state, "query_plan":plans[0] if plans else {"operation":"unsupported"},"all_plans":tagged}


# ─────────────────────────────────────────────────────────────────────────────
#  NODE 3: QUERY EXECUTOR
# ─────────────────────────────────────────────────────────────────────────────

async def query_executor_node(state: AgentState) -> dict:
    all_plans   = state.get("all_plans",[])
    order_draft = state.get("order_draft") or {}
    all_results = []
    READ = {"menu_read","offers_read","popular_items","order_track","customer_read","analytics_read"}

    for entry in all_plans:
        intent=entry.get("intent",""); action=entry.get("action","")
        plan=entry.get("plan",{}); task=entry.get("task",{}); op=plan.get("operation","")

        if op=="conversation" or intent=="conversation":
            # Hard block: customer tried staff/restricted action
            if action == "access_denied_customer":
                all_results.append({"intent":intent,"action":action,"result":"ACCESS_DENIED_CUSTOMER"}); continue
            all_results.append({"intent":intent,"action":action,"result":"CONVERSATION"}); continue
        if op=="access_denied":
            all_results.append({"intent":intent,"action":action,"result":"ACCESS_DENIED"}); continue
        if op=="no_items":
            all_results.append({"intent":intent,"action":action,"result":"NO_ITEMS"}); continue
        if op=="no_feedback":
            all_results.append({"intent":intent,"action":action,"result":"FEEDBACK_EMPTY"}); continue
        if op=="items_unavailable":
            items_str = ", ".join(plan.get("items",[]))
            all_results.append({"intent":intent,"action":action,"result":f"ITEMS_UNAVAILABLE:{items_str}"}); continue
        if op=="need_customer_info":
            draft = {"order_id":task.get("_order_id"),"items":task.get("_enriched_items",[]),
                     "total":task.get("_total",0),"eta":task.get("_eta",30),
                     "prep_time":task.get("_prep_time",20),
                     "delivery_time":task.get("_delivery_time",10),
                     "unavailable":task.get("_unavailable",[]),
                     "payment_method":task.get("payment_method") or "cash",
                     "notes":task.get("notes"),
                     "customer_name":task.get("customer_name") or "",
                     "customer_phone":task.get("customer_phone") or "",
                     "customer_address":task.get("customer_address") or ""}
            packed = json.dumps({"type":"NEED_CUSTOMER_INFO","draft":draft}, ensure_ascii=False)
            return {**state,"db_result":packed,"order_draft":draft,"conv_stage":"await_more"}
        if op=="unsupported":
            all_results.append({"intent":intent,"action":action,"result":"ERROR:Query generate nahi ho saka."}); continue

        # ── order_modify: fetch → merge → update ──────────────────────────────
        if op == "order_modify":
            oid   = plan.get("order_id")
            phone = plan.get("phone")
            add_items = plan.get("add_items", [])

            # 1. Fetch existing order
            filt = {"order_id": oid} if oid else {"customer_phone": phone}
            fetch = await execute_plan({"operation":"find","collection":"orders",
                                        "filter":filt,"limit":1})
            if not fetch["ok"] or not fetch["results"]:
                all_results.append({"intent":intent,"action":action,
                                     "result":f"ERROR:Order {'#'+oid if oid else ''} nahi mila."}); continue
            existing = fetch["results"][0]
            ex_status = existing.get("status","received")
            if ex_status in ("ready","dispatched","delivered","cancelled"):
                all_results.append({"intent":intent,"action":action,
                                     "result":f"ERROR:Order #{oid} already {ex_status} hai — ab modify nahi ho sakta."}); continue

            # 2. Enrich new items to add
            enriched_new, _, _pt, _dt, unavail_new = await _enrich(add_items) if add_items else ([], 0, 0, 0, [])

            # 3. Merge: start with existing items
            merged = list(existing.get("items", []))

            # Remove items first
            remove_names = {r.get("name","").lower() for r in plan.get("remove_items",[])}
            if remove_names:
                merged = [i for i in merged if i.get("name","").lower() not in remove_names]

            # Add/increase new items
            for new_it in enriched_new:
                found = False
                for ex_it in merged:
                    if ex_it.get("name","").lower() == new_it["name"].lower():
                        ex_it["qty"]      += new_it["qty"]
                        ex_it["subtotal"]  = round(ex_it["price"] * ex_it["qty"], 2)
                        found = True; break
                if not found:
                    merged.append(new_it)

            if not merged:
                all_results.append({"intent":intent,"action":action,
                                     "result":"ERROR:Sab items remove ho gaye — order empty ho gaya. Pehle cancel karein."}); continue

            # 4. Recalculate total
            new_total = round(sum(i.get("subtotal",0) for i in merged), 2)
            max_prep  = max((i.get("prep_time", 20) for i in merged), default=20)
            new_eta   = max_prep + 10  # max item prep_time + 10 min fixed delivery

            # 5. Update DB
            actual_oid = existing.get("order_id", oid)
            upd = await execute_plan({
                "operation": "update_one",
                "collection": "orders",
                "filter": {"order_id": actual_oid},
                "update": {"$set": {
                    "items":        merged,
                    "total_amount": new_total,
                    "estimated_time": new_eta,
                    "updated_at":   "__TODAY_START__"
                }}
            })
            if not upd["ok"]:
                all_results.append({"intent":intent,"action":action,
                                     "result":f"ERROR:{upd.get('error','Update failed')}"}); continue

            payload = {
                "type":        "ORDER_MODIFIED",
                "order_id":    actual_oid,
                "items":       merged,
                "total":       new_total,
                "eta":         new_eta,
                "unavailable": unavail_new,
                "payment":     existing.get("payment_method","cash"),
                "address":     existing.get("customer_address",""),
            }
            return {**state, "db_result": json.dumps(payload, ensure_ascii=False, default=str)}

        result = await execute_plan(plan)
        if not result["ok"]:
            all_results.append({"intent":intent,"action":action,"result":f"ERROR:{result.get('error','Unknown')}"}); continue

        r=result["results"]; modified=result.get("modified",0)
        inserted=result.get("inserted",0); upserted=result.get("upserted",0)

        if r==[] and intent in READ:
            all_results.append({"intent":intent,"action":action,"result":f"EMPTY:{action}"}); continue

        if r:
            eo={"intent":intent,"action":action,"result":r}
            if intent=="order_place":
                eo.update({"order_id":task.get("_order_id"),"enriched_items":task.get("_enriched_items",[]),
                           "total":task.get("_total",0),"eta":task.get("_eta",30),
                           "prep_time":task.get("_prep_time",20),"delivery_time":task.get("_delivery_time",10),
                           "unavailable":task.get("_unavailable",[]),
                           "payment_method":task.get("payment_method") or "cash",
                           "customer_address":task.get("customer_address")})
            all_results.append(eo)
        else:
            ops = ",".join(filter(None,[
                f"inserted:{inserted}" if inserted else "",
                f"modified:{modified}" if modified else "",
                f"upserted:{upserted}" if upserted else ""])) or "no_change"
            if intent == "order_cancel":
                oid = task.get("order_id") or task.get("customer_phone","?")
                msg = f"Order #{oid} cancel ho gaya. ❌ Aapka order successfully cancel kar diya gaya."
                all_results.append({"intent":intent,"action":action,"result":f"STATUS_UPDATED:{oid}|{msg}"}); continue
            if intent == "feedback_write":
                all_results.append({"intent":intent,"action":action,"result":"FEEDBACK_SAVED"}); continue
            if intent == "order_update":
                oid=task.get("order_id","?"); ns=task.get("new_status","updated")
                SE={"received":"📥","preparing":"👨‍🍳","ready":"✅","dispatched":"🚗","delivered":"✓","cancelled":"❌"}
                msg=f"Order #{oid} status update: {SE.get(ns,'')} {ns.title()}"
                all_results.append({"intent":intent,"action":action,"result":f"STATUS_UPDATED:{oid}|{msg}"}); continue
            eo={"intent":intent,"action":action,"result":{"status":"OK","ops":ops}}
            if intent=="order_place":
                eo.update({"order_id":task.get("_order_id"),"enriched_items":task.get("_enriched_items",[]),
                           "total":task.get("_total",0),"eta":task.get("_eta",30),
                           "prep_time":task.get("_prep_time",20),"delivery_time":task.get("_delivery_time",10),
                           "unavailable":task.get("_unavailable",[]),
                           "payment_method":task.get("payment_method") or "cash",
                           "customer_address":task.get("customer_address")})
            all_results.append(eo)

    if not all_results:
        return {**state,"db_result":"ERROR:Koi result nahi mila."}

    if len(all_results)==1:
        entry=all_results[0]; r=entry["result"]
        intent=entry.get("intent",""); action=entry.get("action","")
        SPEC=("EMPTY:","ERROR:","NO_ITEMS","CONVERSATION","ITEMS_UNAVAILABLE:","STATUS_UPDATED:","ACCESS_DENIED","FEEDBACK_EMPTY","FEEDBACK_SAVED")
        if isinstance(r,str) and any(r.startswith(p) for p in SPEC):
            return {**state,"db_result":r}
        if intent=="order_place":
            p={"type":"ORDER_PLACED","order_id":entry.get("order_id"),"items":entry.get("enriched_items",[]),
               "total":entry.get("total",0),"eta":entry.get("eta",30),
               "prep_time":entry.get("prep_time",20),"delivery_time":entry.get("delivery_time",10),
               "payment":entry.get("payment_method","cash"),
               "address":entry.get("customer_address"),"unavailable":entry.get("unavailable",[])}
            return {**state,"db_result":json.dumps(p,ensure_ascii=False,default=str),"conv_stage":"","order_draft":{}}
        if intent=="menu_read" and isinstance(r,list):
            return {**state,"db_result":json.dumps({"type":"MENU_DATA","items":r},ensure_ascii=False)}
        if intent=="offers_read" and isinstance(r,list):
            return {**state,"db_result":json.dumps({"type":"OFFERS_DATA","items":r},ensure_ascii=False)}
        if intent=="popular_items" and isinstance(r,list):
            return {**state,"db_result":json.dumps({"type":"POPULAR_ITEMS","items":r},ensure_ascii=False)}
        if isinstance(r,list):
            return {**state,"db_result":json.dumps({"intent":intent,"action":action,"data":r},ensure_ascii=False,default=str)}
        if isinstance(r,dict):
            return {**state,"db_result":json.dumps(r,ensure_ascii=False,default=str)}
        return {**state,"db_result":str(r)}

    return {**state,"db_result":json.dumps([{"intent":e["intent"],"action":e["action"],"result":e["result"]}
                                             for e in all_results],ensure_ascii=False,default=str)}


# ─────────────────────────────────────────────────────────────────────────────
#  NODE 4: RESPONDER
# ─────────────────────────────────────────────────────────────────────────────

async def responder_node(state: AgentState) -> dict:
    db_result   = state.get("db_result","")
    user_msg    = state["user_message"]
    tasks       = state.get("tasks",[])
    action      = tasks[0].get("action","") if tasks else ""
    user_role   = state.get("user_role","customer")
    order_draft = state.get("order_draft") or {}
    conv_stage  = state.get("conv_stage","")
    history     = state.get("conversation_history") or []

    # ── access_denied_customer — blocked restricted request (customers only) ────
    if action == "access_denied_customer" and user_role != "staff":
        import random as _rand
        # Specific response based on what they asked
        user_lower = user_msg.lower()
        if any(w in user_lower for w in ["menu","item","dish","halwa","karahi","add","daal","update","badlo"]):
            responses = [
                "Shukriya aapke suggestion ke liye! Main yeh feedback restaurant management tak zaroor pohnchaonga. Menu updates unhi ke haath mein hain. 😊",
                "Bohat acha suggestion hai! Hum restaurant team ko batayenge — woh menu decisions leti hai. Koi aur cheez chahiye? 🍛",
                "Feedback ke liye shukriya! Restaurant staff ko inform kar diya jaye ga. Filhaal menu dekhna chahte hain?",
            ]
        elif any(w in user_lower for w in ["customer","order","data","kisi","baki","doosre","personal","detail","info"]):
            responses = [
                "Kisi bhi customer ki personal information ya orders share karna mere liye mumkin nahi — yeh privacy ke against hai. Apna koi order track karna ho to bataiye! 🔒",
                "Dusre customers ki details main nahi de sakta — yeh ek privacy matter hai. Apni koi cheez chahiye? 😊",
                "Sorry! Kisi aur customer ka data share nahi kar sakta. Apna order, menu, ya deals — kuch bhi poochhein!",
            ]
        else:
            responses = [
                "Yeh kaam sirf restaurant staff kar sakta hai. Menu, orders, ya deals mein kuch chahiye? 😊",
                "Is cheez mein main help nahi kar sakta. Lekin order dena, track karna, ya menu dekhna ho — zaroor bataiye!",
            ]
        return {**state, "final_response": _rand.choice(responses)}

    # ── ask_what_to_add — customer said haan but didn't name anything ────────
    if action == "ask_what_to_add":
        return {**state, "final_response":"Zaroor! Kya add karna chahte hain? Misal ke taur par: '1 ice cream, 2 naan'"}

    # ── apply_modification — _new_items comes from CART_DECISION_PROMPT ──────
    if action == "apply_modification":
        new_items = tasks[0].get("_new_items", []) if tasks else []
        if not new_items:
            return {**state, "final_response":_cart_summary(order_draft), "conv_stage":"await_more"}
        try:
            enriched, total, prep_time, delivery_time, unavail = await _enrich(new_items)
            eta = prep_time + delivery_time
            order_draft["items"] = enriched
            order_draft["total"] = total
            order_draft["eta"]   = eta
            unavail_msg = (f"\n⚠️  Yeh items available nahi, hataye gaye: {', '.join(unavail)}"
                           if unavail else "")
            return {**state, "order_draft":order_draft, "conv_stage":"await_more",
                    "final_response":_cart_summary(order_draft) + unavail_msg}
        except Exception:
            return {**state, "final_response":_cart_summary(order_draft), "conv_stage":"await_more"}

    # ── Multi-turn prompts ────────────────────────────────────────────────────
    if action == "collect_name":
        return {**state,"final_response":"📝 Aapka naam batayein please:"}
    if action == "collect_phone":
        name = order_draft.get("customer_name","").title()
        return {**state,"final_response":f"Shukriya {name}! 📱 Apna phone number batayein (e.g. 0300-1234567):"}
    if action == "collect_address":
        return {**state,"final_response":"📍 Delivery address batayein (ghar/mohalla, shehar):"}
    if action == "show_bill":
        return {**state,"final_response":_bill(order_draft)}
    if action == "order_cancelled_by_user":
        return {**state,"final_response":"❌ Order cancel kar diya gaya. Koi aur khidmat chahiye? 😊","conv_stage":"","order_draft":{}}

    # ── NEED_CUSTOMER_INFO → show cart + ask "koi aur cheez?" ────────────────
    try:
        p = json.loads(db_result)
        if isinstance(p,dict) and p.get("type")=="NEED_CUSTOMER_INFO":
            draft = p.get("draft",{})
            its   = draft.get("items",[]); tot = draft.get("total",0)
            lines = ["✅ Items confirm! Aapka order:\n"]
            for it in its:
                lines.append(f"  {it['qty']}x {it['name'].title()} — Rs {it['subtotal']:,.0f}")
            lines.append(f"\n💰 Total: Rs {tot:,.0f}")
            if draft.get("unavailable"):
                lines.append(f"⚠️  Kuch items available nahi (hataye gaye): {', '.join(draft['unavailable'])}")
            lines.append("\nKoi aur cheez add karni hai? (haan / nahi)")
            return {**state,"final_response":"\n".join(lines),"conv_stage":"await_more","order_draft":draft}
    except Exception: pass

    # ── Popular items — most ordered dishes (customer query) ─────────────────
    try:
        p = json.loads(db_result)
        if isinstance(p, dict) and p.get("type") == "POPULAR_ITEMS":
            items = p.get("items", [])
            # Filter out null/empty names that slipped through
            items = [row for row in items if row.get("_id") and isinstance(row["_id"], str) and row["_id"].strip()]
            if not items:
                return {**state, "final_response": (
                    "😊 Hamare sab dishes kaafi popular hain! Abhi order data available nahi hai.\n"
                    "'menu dikhao' likh kar hamara poora menu dekh sakte hain."
                )}
            MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            lines = [
                "🌟 HAMARE SABSE POPULAR DISHES",
                "─" * 36,
            ]
            for i, row in enumerate(items[:5]):
                name  = row["_id"].title()
                qty   = row.get("qty", 0)
                medal = MEDALS[i] if i < len(MEDALS) else f"{i+1}."
                lines.append(f"  {medal}  {name}")
                lines.append(f"       {qty} baar order kiya gaya")
            lines.append("─" * 36)
            top_name = items[0]["_id"].title()
            lines.append(f"\n✨ Sabse zyada pasand: {top_name}!")
            lines.append("💬 Order: '2 " + items[0]["_id"] + " order karo'")
            return {**state, "final_response": "\n".join(lines)}
    except Exception:
        pass

    # ── Menu ─────────────────────────────────────────────────────────────────
    try:
        p = json.loads(db_result)
        if isinstance(p,dict) and p.get("type")=="MENU_DATA":
            its = p.get("items",[])
            if not its:
                return {**state,"final_response":NOT_FOUND_MENU}
            return {**state,"final_response":_menu_display(its)}
    except Exception: pass

    # ── Offers — DIRECT display, no LLM ─────────────────────────────────────
    try:
        p = json.loads(db_result)
        if isinstance(p,dict) and p.get("type")=="OFFERS_DATA":
            return {**state,"final_response":_offers_display(p.get("items",[]))}
    except Exception: pass

    # ── Order placed ──────────────────────────────────────────────────────────
    try:
        p = json.loads(db_result)
        if isinstance(p,dict) and p.get("type")=="ORDER_PLACED":
            PAY={"cash":"Cash on Delivery","easypaisa":"EasyPaisa","jazzcash":"JazzCash","card":"Card"}
            oid=p.get("order_id","?"); its=p.get("items",[]); tot=p.get("total",0)
            eta=p.get("eta",30); pay=PAY.get(p.get("payment","cash"),"Cash on Delivery")
            lines=[f"### ✅ ORDER CONFIRMED! `#{oid}`",
                   "---",
                   "**📦 ITEMS:**"]
            for it in its:
                lines.append(f"- {it.get('qty',1)}x **{it.get('name','').title()}** — Rs {it.get('subtotal',0):,.0f}")
            lines+=[f"\n**💰 TOTAL: Rs {tot:,.0f}**",
                    f"**🕐 ETA:** ~{eta} minutes",
                    f"**💳 Payment:** {pay}"]
            if p.get("address"): lines.append(f"**📍 Address:** {p['address']}")
            if p.get("unavailable"):
                lines.append(f"\n⚠️ **Not Available:** {', '.join(p['unavailable'])}")
            lines.append("\n🙏 Order receive ho gaya! Tayari par inform karein ge.")
            return {**state,"final_response":"\n".join(lines),"conv_stage":"","order_draft":{}, "res_type":"bill", "res_data":p}
    except Exception: pass

    # ── Order modified (add/remove items from placed order) ─────────────────
    try:
        p = json.loads(db_result)
        if isinstance(p,dict) and p.get("type")=="ORDER_MODIFIED":
            PAY={"cash":"Cash on Delivery","easypaisa":"EasyPaisa","jazzcash":"JazzCash","card":"Card"}
            oid  = p.get("order_id","?")
            its  = p.get("items",[])
            tot  = p.get("total",0)
            eta  = p.get("eta",30)
            pay  = PAY.get(p.get("payment","cash"),"Cash on Delivery")
            addr = p.get("address","")
            unavail = p.get("unavailable",[])
            lines = [
                f"### ✏️ ORDER UPDATED! `#{oid}`",
                "---",
                "**📦 UPDATED ITEMS:**",
            ]
            for it in its:
                lines.append(f"- {it.get('qty',1)}x **{it.get('name','').title()}** — Rs {it.get('subtotal',0):,.0f}")
            lines += [
                f"\n**💰 NEW TOTAL: Rs {tot:,.0f}**",
                f"**🕐 ETA:** ~{eta} minutes",
                f"**💳 Payment:** {pay}",
            ]
            if addr: lines.append(f"**📍 Address:** {addr}")
            if unavail:
                lines.append(f'\n⚠️ **Unavailable:** {", ".join(unavail)}')
            lines += [
                "\n✅ Order update ho gaya! Kitchen ko inform kar diya gaya.",
            ]
            return {**state, "final_response": "\n".join(lines), "res_type":"bill", "res_data":p}
    except Exception: pass

    # ── Staff write success ───────────────────────────────────────────────────
    try:
        p = json.loads(db_result)
        if isinstance(p,dict) and p.get("status")=="OK":
            ops     = p.get("ops","")
            intent_ = tasks[0].get("intent","") if tasks else ""
            action_ = tasks[0].get("action","") if tasks else ""
            if "insert" in ops:
                if intent_ == "offers_write":
                    msg = "✅ Offer successfully add ho gaya! Customer chatbot mein ab dikhega."
                elif intent_ == "menu_write":
                    msg = "✅ Menu item add ho gaya! Customers ab order kar sakte hain."
                else:
                    msg = "✅ Record add ho gaya!"
            elif "modified" in ops or "upsert" in ops:
                if intent_ == "menu_write":
                    msg = "✅ Menu update ho gaya!"
                elif intent_ == "offers_write":
                    msg = "✅ Offer update ho gaya!"
                elif intent_ == "order_update":
                    ns  = tasks[0].get("new_status","") if tasks else ""
                    oid = tasks[0].get("order_id","?") if tasks else "?"
                    STATUS_MSGS = {
                        "preparing":  f"👨‍🍳 Order #{oid} → Preparing! Kitchen shuru ho gaya.",
                        "ready":      f"✅ Order #{oid} → Ready! Delivery ke liye tayar.",
                        "dispatched": f"🚗 Order #{oid} → Dispatched! Rider rawan ho gaya.",
                        "delivered":  f"✓  Order #{oid} → Delivered! Order complete ho gaya.",
                        "cancelled":  f"❌ Order #{oid} → Cancelled.",
                    }
                    msg = STATUS_MSGS.get(ns, f"✅ Order #{oid} update ho gaya!")
                else:
                    msg = "✅ Successfully update ho gaya!"
            else:
                msg = "✅ Operation complete."
            return {**state,"final_response":msg}
    except Exception: pass

    if db_result=="FEEDBACK_EMPTY":
        return {**state,"final_response":"😊 Feedback dene ke liye apni baat likhein — kya acha laga, kya nahi laga, ya koi suggestion ho. Hum zaroor improve karein ge! 🙏"}
    if db_result=="FEEDBACK_SAVED":
        return {**state,"final_response":"✅ Shukriya aapki feedback ka! Aapki baat humein mil gayi — hum isko improve karne ke liye use karein ge. 🙏\n😊 Kuch aur help chahiye?"}

    # ── Special string results ────────────────────────────────────────────────
    if db_result=="ACCESS_DENIED":
        return {**state,"final_response":"⛔ Yeh feature sirf restaurant staff ke liye hai. Staff panel se login karein."}
    if db_result=="ACCESS_DENIED_CUSTOMER":
        import random as _rand
        responses = [
            "Yeh kaam sirf restaurant staff kar sakta hai — main customer orders, menu, aur deals mein help kar sakta hoon. Kuch order karna hai? 😊",
            "Is cheez ka access sirf staff ko hai. Menu dekhna, order dena, ya track karna ho — zaroor bataiye!",
            "Yeh meri service mein nahi aata. Lekin agar menu, order, ya deals ka koi sawaal ho to bilkul poochhein! 🍛",
        ]
        return {**state,"final_response":_rand.choice(responses)}
    if db_result=="NO_ITEMS":
        return {**state,"final_response":"Koi item specify nahi kiya.\nExample: '2 chicken biryani order karo' 😊"}
    if db_result.startswith("ITEMS_UNAVAILABLE:"):
        items=db_result.replace("ITEMS_UNAVAILABLE:","").strip()
        return {**state,"final_response":(f"😔 Maafi! Yeh items abhi available nahi hain: {items}\n"
                                          "'menu dikhao' likh kar available items check karein. 🙏")}
    if db_result.startswith("STATUS_UPDATED:"):
        msg=db_result.replace("STATUS_UPDATED:","").split("|",1)
        return {**state,"final_response":msg[1] if len(msg)>1 else msg[0]}
    if db_result.startswith("ERROR:"):
        err_detail = db_result.replace("ERROR:","").strip()
        if user_role == "staff":
            return {**state,"final_response":f"⚠️ Query execute nahi ho saki:\n{err_detail}\n\nDobara try karein ya query simplify karein."}
        else:
            return {**state,"final_response":"😔 Is waqt yeh maloomat hasil nahi ho saki. Thodi der baad dobara try karein. 🙏"}
    if db_result.startswith("EMPTY:"):
        a = db_result.replace("EMPTY:","").lower()
        if user_role == "staff":
            # Staff-specific empty messages
            if any(x in a for x in ("top_items","top items","best sell")):
                return {**state,"final_response":"📭 Is period mein koi order record nahi — top items calculate nahi ho sake."}
            if any(x in a for x in ("top_customer","top customer")):
                return {**state,"final_response":"👤 Abhi tak koi customer record nahi mila."}
            if any(x in a for x in ("all_orders","daily","today","aaj")):
                return {**state,"final_response":"📭 Aaj abhi tak koi order nahi aaya."}
            if any(x in a for x in ("weekly","week","hafte")):
                return {**state,"final_response":"📭 Is hafte koi order nahi mila."}
            if any(x in a for x in ("monthly","month","mahine")):
                return {**state,"final_response":"📭 Is mahine koi order nahi mila."}
            if any(x in a for x in ("customer","list_customer")):
                return {**state,"final_response":"👤 Koi customer record nahi mila."}
            if any(x in a for x in ("feedback",)):
                return {**state,"final_response":"💬 Abhi tak koi customer feedback nahi mila."}
            return {**state,"final_response":"📭 Is query ke liye koi data nahi mila."}
        msg = next((v for k,v in EMPTY_MAP.items() if k in a), NOT_FOUND_GENERIC)
        return {**state,"final_response":msg}

    # ── Out-of-scope: classified by router as outside restaurant domain ──────────
    if action == "out_of_scope":
        if user_role == "staff":
            oos_responses = [
                "Main sirf restaurant operations mein help kar sakta hoon — sales, orders, menu, customers. Kuch aur chahiye?",
                "Is topic par assist nahi kar sakta. Report, menu update, ya order query ho to zaroor bataiye! 📊",
                "Restaurant AI hoon — general questions mere scope se bahar hain. Koi business query ho? 😊",
            ]
        else:
            oos_responses = [
                "Yeh meri expertise nahi — main sirf is restaurant ke baare mein help kar sakta hoon! 😊 Kuch order karna hai ya menu dekhna hai?",
                "Main ek restaurant chatbot hoon — in cheezon mein help nahi kar sakta. Khaane ka koi sawaal ho to zaroor poochhein! 🍛",
                "Is topic par kuch nahi bata sakta. Lekin menu, orders, ya deals ke baare mein zaroor help karunga! 😊",
                "Yeh mera domain nahi. Order dena ho, track karna ho, ya menu dekhna ho — main haazir hoon! 🍛",
            ]
        import random as _r
        return {**state, "final_response": _r.choice(oos_responses)}

    # ── Conversation ──────────────────────────────────────────────────────────
    if db_result=="CONVERSATION":
        prior = history[-8:]
        if user_role == "staff":
            sys_msg = (STAFF_RESPONDER_PROMPT +
                       "\nIf staff is greeting or asking general question, respond warmly in 1 line.")
        else:
            sys_msg = (RESPONDER_PROMPT +
                       "\nBe natural and brief. No filler phrases. "
                       "If greeting, reply warmly in 1 line. "
                       "Never start with 'Janab' or 'Meherbani se'. "
                       "Respond in Roman Urdu + English.")
        msgs = [{"role":"system","content":sys_msg}]
        for h in prior: msgs.append({"role":h["role"],"content":h["content"]})
        msgs.append({"role":"user","content":user_msg})
        res = await groq_client.chat.completions.create(messages=msgs,model=MODEL,temperature=0.4,max_tokens=300)
        return {**state,"final_response":res.choices[0].message.content.strip()}

    # ── Staff-specific rich formatters (avoid LLM hallucination on data) ───────
    if user_role == "staff":
        try:
            p = json.loads(db_result)
            if isinstance(p, dict):
                intent_str = tasks[0].get("intent","") if tasks else ""
                action_str = tasks[0].get("action","") if tasks else ""
                data_list  = p.get("data", p.get("results", []))

                # ── CUSTOMER intent: check FIRST before analytics (both have total_orders) ──
                if intent_str == "customer_read":
                    if action_str == "feedback" or ("message" in db_result and "rating" in db_result):
                        return {**state, "final_response": _staff_feedback_display(data_list)}
                    if isinstance(data_list, list) and data_list:
                        if "order_id" in str(data_list[0]):
                            return {**state, "final_response": _staff_orders_display(data_list)}
                        return {**state, "final_response": _staff_customer_display(data_list)}
                    return {**state, "final_response": "👤 Koi customer record nahi mila."}

                # ── Top customers: check BEFORE analytics formatter to avoid misrouting ──
                if (action_str in ("top_customers","top_customer") or
                        any(w in user_msg.lower() for w in
                            ("top customer","sabse zyada order","best customer","loyal customer","regular customer","kis customer","konsa customer"))):
                    if isinstance(data_list, list) and data_list:
                        return {**state, "final_response": _staff_customer_display(data_list, "TOP CUSTOMERS 🏆")}

                # ── Orders list (analytics: all_orders, pending_orders, order_detail) ──
                if isinstance(data_list, list) and data_list and "order_id" in str(data_list[0]):
                    formatted = _staff_orders_display(data_list)
                    if formatted:
                        return {**state, "final_response": formatted}

                # ── Analytics summary (aggregate: revenue, top items, status breakdown) ──
                if intent_str == "analytics_read":
                    formatted = _staff_analytics_display(p, user_msg)
                    if formatted:
                        return {**state, "final_response": formatted}

        except Exception:
            pass

    # ── LLM formats remaining DB results ──────────────────────────────────────
    is_staff = user_role == "staff"
    system_extra = (
        "\nAap STAFF mode mein hain. Data clearly aur professionally dikhao. "
        "Tables ya bullet points use karo. Revenue/orders numbers bold karo. "
        "Roman Urdu + English mix use karo."
    ) if is_staff else ""

    # ── Fetch menu context for Responder ──────────────────────────────────────
    menu_context = await _get_menu_context()

    msgs=[{"role":"system","content":RESPONDER_PROMPT + f"\n\nCURRENT MENU CONTEXT:\n{menu_context}" + system_extra},
          {"role":"user","content":(
              f"User ne kaha: {user_msg}\n\n"
              f"=== DB DATA ===\n{db_result}\n=== END ===\n\n"
              "Yeh data Roman Urdu mein professional tarike se dikhao.\n"
              "Agar data empty hai ya kuch nahi mila to clearly bolo kya nahi mila — 'try again later' mat kaho.\n"
              "Agar user ne kuch aisa poocha jo restaurant se related nahi, to politely out-of-scope bolao aur redirect karo.\n"
              "DB mein jo nahi hai wo invent mat karo."
              + (" Numbers aur stats clearly format karo." if is_staff else "")
          )}]
    res=await groq_client.chat.completions.create(messages=msgs,model=MODEL,temperature=0.2,max_tokens=800)
    return {**state,"final_response":res.choices[0].message.content.strip()}