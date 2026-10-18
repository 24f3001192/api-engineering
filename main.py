from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import time
import uuid
import base64

app = FastAPI()

# FIXED: allow_credentials is now False, which stops the app from crashing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False, 
    allow_methods=["*"],
    allow_headers=["*"],
)

# Your specific assigned values
TOTAL_ORDERS = 41
RATE_LIMIT = 19
RATE_WINDOW_SECONDS = 10.0

# In-memory storage for our store data
ORDERS_DB = [{"id": i} for i in range(1, TOTAL_ORDERS + 1)]
idempotency_store = {}
client_requests = {}

# 1. Spam Blocker (Rate Limiting Middleware)
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_id = request.headers.get("x-client-id")
    
    if client_id:
        now = time.time()
        # Get this user's click history
        history = client_requests.get(client_id, [])
        # Remove old clicks that happened more than 10 seconds ago
        history = [t for t in history if now - t < RATE_WINDOW_SECONDS]
        
        # If they still have 19 or more clicks in the last 10 seconds, block them
        if len(history) >= RATE_LIMIT:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests"},
                headers={"Retry-After": str(int(RATE_WINDOW_SECONDS))}
            )
        
        # Otherwise, record this new click and let them through
        history.append(now)
        client_requests[client_id] = history
        
    return await call_next(request)

# 2. Double-Charge Protection (Idempotent POST)
@app.post("/orders", status_code=201)
async def create_order(idempotency_key: str = Header(None)):
    # If we have seen this exact key before, return the existing order
    if idempotency_key and idempotency_key in idempotency_store:
        return {"id": idempotency_store[idempotency_key]}
    
    # Otherwise, create a brand new order ID
    new_id = str(uuid.uuid4())
    
    # Save it to memory so we remember it next time
    if idempotency_key:
        idempotency_store[idempotency_key] = new_id
        
    return {"id": new_id}

# 3. Page Flipping (Cursor Pagination)
@app.get("/orders")
async def get_orders(limit: int = 10, cursor: str = None):
    start_idx = 0
    
    # If the user gives us a bookmark (cursor), decode it to find our starting place
    if cursor:
        try:
            start_idx = int(base64.b64decode(cursor).decode('utf-8'))
        except Exception:
            start_idx = 0
            
    end_idx = start_idx + limit
    
    # Grab the specific slice of items from our database
    items = ORDERS_DB[start_idx:end_idx]
    
    # Create the next bookmark if there are still more items left in the store
    next_cursor = None
    if end_idx < TOTAL_ORDERS:
        next_cursor = base64.b64encode(str(end_idx).encode('utf-8')).decode('utf-8')
        
    return {
        "items": items,
        "next_cursor": next_cursor
    }