from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import time
import uuid
import base64

app = FastAPI()

# FIXED: Explicitly exposing the Retry-After header to the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After", "*"] 
)

# Assigned values
TOTAL_ORDERS = 41
RATE_LIMIT = 19
RATE_WINDOW_SECONDS = 10.0

ORDERS_DB = [{"id": i} for i in range(1, TOTAL_ORDERS + 1)]
idempotency_store = {}
client_requests = {}

# 1. Spam Blocker
def check_rate_limit(x_client_id: str = Header(None)):
    if x_client_id:
        now = time.time()
        # Get history and filter out old clicks
        history = client_requests.get(x_client_id, [])
        history = [t for t in history if now - t < RATE_WINDOW_SECONDS]
        
        if len(history) >= RATE_LIMIT:
            # Safely raise an exception with the Retry-After header
            raise HTTPException(
                status_code=429,
                detail="Too Many Requests",
                headers={"Retry-After": str(int(RATE_WINDOW_SECONDS))}
            )
            
        history.append(now)
        client_requests[x_client_id] = history

# 2. Double-Charge Protection
@app.post("/orders", status_code=201, dependencies=[Depends(check_rate_limit)])
async def create_order(idempotency_key: str = Header(None)):
    if idempotency_key and idempotency_key in idempotency_store:
        return {"id": idempotency_store[idempotency_key]}
    
    new_id = str(uuid.uuid4())
    if idempotency_key:
        idempotency_store[idempotency_key] = new_id
        
    return {"id": new_id}

# 3. Page Flipping
@app.get("/orders", dependencies=[Depends(check_rate_limit)])
async def get_orders(limit: int = 10, cursor: str = None):
    start_idx = 0
    if cursor:
        try:
            start_idx = int(base64.b64decode(cursor).decode('utf-8'))
        except Exception:
            start_idx = 0
            
    end_idx = start_idx + limit
    items = ORDERS_DB[start_idx:end_idx]
    
    next_cursor = None
    if end_idx < TOTAL_ORDERS:
        next_cursor = base64.b64encode(str(end_idx).encode('utf-8')).decode('utf-8')
        
    return {
        "items": items,
        "next_cursor": next_cursor
    }