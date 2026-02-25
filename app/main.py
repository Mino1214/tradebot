from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import init_db
from app.routers import webhook, params, trade, dashboard, dashboard_b, admin_c_bot


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    # shutdown if needed


app = FastAPI(title="TradeBot", lifespan=lifespan)
app.include_router(webhook.router)
app.include_router(params.router)
app.include_router(trade.router)
app.include_router(dashboard.router)
app.include_router(dashboard_b.router)
app.include_router(admin_c_bot.router)


@app.get("/health")
def health():
    return {"status": "ok"}
