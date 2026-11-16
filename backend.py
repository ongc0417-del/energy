#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
能量宝后端 API
运行: uvicorn backend:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from datetime import datetime
from typing import Optional
import json

app = FastAPI(title="能量宝后台")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "database.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE,
            balance REAL DEFAULT 0,
            claim_count INTEGER DEFAULT 0,
            created_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE,
            user_id TEXT,
            type TEXT,
            amount REAL,
            address TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_id TEXT UNIQUE,
            from_address TEXT,
            amount REAL,
            user_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS claimed_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT UNIQUE,
            claim_count INTEGER DEFAULT 1,
            last_claim TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT,
            created_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    # 默认设置
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('energy_price', '2')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('swap_rate', '3.15')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('free_count', '3')")
    conn.commit()
    conn.close()

init_db()

# ============ 数据总览 ============
@app.get("/api/dashboard")
def get_dashboard():
    conn = get_db()
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    c.execute("SELECT COUNT(*) FROM users WHERE created_at LIKE ?", (f"{today}%",))
    today_users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM orders WHERE created_at LIKE ?", (f"{today}%",))
    today_orders = c.fetchone()[0]
    
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE created_at LIKE ? AND status = 'completed'", (f"{today}%",))
    today_income = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    c.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 10")
    recent = [dict(row) for row in c.fetchall()]
    
    conn.close()
    return {
        "today_users": today_users,
        "today_orders": today_orders,
        "today_income": today_income,
        "total_users": total_users,
        "recent_orders": recent
    }

# ============ 用户管理 ============
@app.get("/api/users")
def get_users(search: Optional[str] = None):
    conn = get_db()
    c = conn.cursor()
    if search:
        c.execute("SELECT * FROM users WHERE user_id LIKE ? ORDER BY created_at DESC", (f"%{search}%",))
    else:
        c.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT 100")
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    return users

@app.post("/api/users/{user_id}/balance")
def update_balance(user_id: str, amount: float):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    return {"success": True}

# ============ 订单管理 ============
@app.get("/api/orders")
def get_orders(type: Optional[str] = None):
    conn = get_db()
    c = conn.cursor()
    if type and type != "all":
        c.execute("SELECT * FROM orders WHERE type = ? ORDER BY created_at DESC LIMIT 100", (type,))
    else:
        c.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 100")
    orders = [dict(row) for row in c.fetchall()]
    conn.close()
    return orders

class OrderCreate(BaseModel):
    user_id: str
    type: str
    amount: float
    address: str

@app.post("/api/orders")
def create_order(order: OrderCreate):
    conn = get_db()
    c = conn.cursor()
    order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}"
    c.execute('''
        INSERT INTO orders (order_id, user_id, type, amount, address, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (order_id, order.user_id, order.type, order.amount, order.address, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"order_id": order_id}

# ============ 充值记录 ============
@app.get("/api/deposits")
def get_deposits():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM deposits ORDER BY created_at DESC LIMIT 100")
    deposits = [dict(row) for row in c.fetchall()]
    conn.close()
    return deposits

# ============ 地址管理 ============
@app.get("/api/addresses")
def get_addresses():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM claimed_addresses ORDER BY last_claim DESC LIMIT 100")
    addresses = [dict(row) for row in c.fetchall()]
    conn.close()
    return addresses

@app.post("/api/addresses/{address}/claim")
def claim_address(address: str):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO claimed_addresses (address, claim_count, last_claim)
        VALUES (?, 1, ?)
        ON CONFLICT(address) DO UPDATE SET claim_count = claim_count + 1, last_claim = ?
    ''', (address, datetime.now().isoformat(), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"success": True}

# ============ 发能量 ============
class EnergySend(BaseModel):
    address: str
    count: int

@app.post("/api/energy/send")
def send_energy(data: EnergySend):
    # TODO: 对接真实能量API
    conn = get_db()
    c = conn.cursor()
    order_id = f"ENG{datetime.now().strftime('%Y%m%d%H%M%S')}"
    c.execute('''
        INSERT INTO orders (order_id, user_id, type, amount, address, status, created_at)
        VALUES (?, 'admin', 'energy', ?, ?, 'completed', ?)
    ''', (order_id, data.count * 2, data.address, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"success": True, "message": f"已向 {data.address} 发送 {data.count} 笔能量"}

# ============ 广告管理 ============
@app.get("/api/ads")
def get_ads():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM ads ORDER BY created_at DESC LIMIT 50")
    ads = [dict(row) for row in c.fetchall()]
    conn.close()
    return ads

class AdCreate(BaseModel):
    content: str

@app.post("/api/ads")
def create_ad(ad: AdCreate):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO ads (content, created_at) VALUES (?, ?)", (ad.content, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"success": True}

@app.delete("/api/ads/{ad_id}")
def delete_ad(ad_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM ads WHERE id = ?", (ad_id,))
    conn.commit()
    conn.close()
    return {"success": True}

# ============ 设置 ============
@app.get("/api/settings")
def get_settings():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM settings")
    settings = {row["key"]: row["value"] for row in c.fetchall()}
    conn.close()
    return settings

class SettingUpdate(BaseModel):
    key: str
    value: str

@app.post("/api/settings")
def update_setting(data: SettingUpdate):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (data.key, data.value))
    conn.commit()
    conn.close()
    return {"success": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)