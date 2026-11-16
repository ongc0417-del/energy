#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动入账监控脚本
监听充值地址，有新的 TRX 转入时自动记录
"""

import time
import requests
import sqlite3
from datetime import datetime

# 配置
RECHARGE_ADDRESS = "TYourRechargeAddressHere"  # 改成你的充值地址
CHECK_INTERVAL = 30  # 每 30 秒检查一次
DB_PATH = "database.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_id TEXT UNIQUE,
            from_address TEXT,
            amount REAL,
            timestamp INTEGER,
            credited INTEGER DEFAULT 0,
            user_id TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_latest_transactions():
    """获取充值地址的最新交易"""
    url = f"https://api.trongrid.io/v1/accounts/{RECHARGE_ADDRESS}/transactions"
    params = {"limit": 20, "only_confirmed": True}
    try:
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            return res.json().get("data", [])
    except Exception as e:
        print(f"获取交易失败: {e}")
    return []

def parse_trx_transfer(tx):
    """解析 TRX 转账"""
    if tx.get("raw_data", {}).get("contract", [{}])[0].get("type") != "TransferContract":
        return None
    
    contract = tx["raw_data"]["contract"][0]["parameter"]["value"]
    to_addr = contract.get("to_address")
    # 转换为 base58 地址（简化处理，实际需要解码）
    if not to_addr:
        return None
    
    amount = contract.get("amount", 0) / 1e6  # sun 转 TRX
    from_addr = contract.get("owner_address", "")
    tx_id = tx.get("txID", "")
    timestamp = tx.get("raw_data", {}).get("timestamp", 0)
    
    return {
        "tx_id": tx_id,
        "from_address": from_addr,
        "amount": amount,
        "timestamp": timestamp
    }

def save_deposit(deposit):
    """保存充值记录"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT OR IGNORE INTO deposits (tx_id, from_address, amount, timestamp, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            deposit["tx_id"],
            deposit["from_address"],
            deposit["amount"],
            deposit["timestamp"],
            datetime.now().isoformat()
        ))
        conn.commit()
        if c.rowcount > 0:
            print(f"新充值: {deposit['amount']} TRX 来自 {deposit['from_address'][:8]}...")
            return True
    except Exception as e:
        print(f"保存失败: {e}")
    finally:
        conn.close()
    return False

def monitor():
    """主监控循环"""
    print(f"开始监控充值地址: {RECHARGE_ADDRESS}")
    print(f"检查间隔: {CHECK_INTERVAL} 秒")
    
    init_db()
    seen_txs = set()
    
    while True:
        try:
            txs = get_latest_transactions()
            for tx in txs:
                tx_id = tx.get("txID", "")
                if tx_id in seen_txs:
                    continue
                
                deposit = parse_trx_transfer(tx)
                if deposit and deposit["amount"] >= 1:  # 忽略小额
                    save_deposit(deposit)
                    seen_txs.add(tx_id)
            
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\n监控已停止")
            break
        except Exception as e:
            print(f"错误: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor()