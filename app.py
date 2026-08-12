#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票多因子筛选系统 - 安卓Termux版
支持1-20只股票，多因子打分筛选TOP3
数据源：AKShare
GitHub: https://github.com/你的用户名/stock_screener
"""

import akshare as ak
import pandas as pd
import numpy as np
import time
import requests
import json
import sys
import os
from datetime import datetime, timedelta

# ==================== 配置区域（用户可修改） ====================

# 在这里填入你的股票代码（1-20只，6位数字）
# 示例：['000001', '600519', '300750']
STOCK_CODES = [
    '000001',  # 平安银行
    '000002',  # 万科A
    '000858',  # 五粮液
    '002415',  # 海康威视
    '002594',  # 比亚迪
    '300750',  # 宁德时代
    '600036',  # 招商银行
    '600519',  # 贵州茅台
    '600900',  # 长江电力
    '601318',  # 中国平安
    '601398',  # 工商银行
    '601857',  # 中国石油
    '601166',  # 兴业银行
    '601288',  # 农业银行
    '601328',  # 交通银行
    '600276',  # 恒瑞医药
    '600030',  # 中信证券
    '601688',  # 华泰证券
    '600887',  # 伊利股份
    '603288'   # 海天味业
]

# 飞书机器人Webhook（可选，不填则不推送）
FEISHU_WEBHOOK = ""  # 例如: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"

# Telegram Bot配置（可选）
TELEGRAM_BOT_TOKEN = ""  # 例如: "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
TELEGRAM_CHAT_ID = ""    # 例如: "123456789"

# 是否在终端显示详细结果
VERBOSE = True

# 数据请求间隔（秒），避免请求过快
REQUEST_INTERVAL = 0.3

# ==================== 技术指标计算 ====================

def calc_ma(df, col='close', period=5):
    """计算移动平均线"""
    return df[col].rolling(window=period).mean()

def calc_macd(df, col='close', fast=12, slow=26, signal=9):
    """计算MACD"""
    exp_fast = df[col].ewm(span=fast, adjust=False).mean()
    exp_slow = df[col].ewm(span=slow, adjust=False).mean()
    macd = exp_fast - exp_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - macd_signal
    return macd, macd_signal, macd_hist

def calc_rsi(df, col='close', period=14):
    """计算RSI"""
    delta = df[col].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_kdj(df, n=9, m1=3, m2=3):
    """计算KDJ"""
    low_min = df['low'].rolling(window=n).min()
    high_max = df['high'].rolling(window=n).max()
    rsv = (df['close'] - low_min) / (high_max - low_min) * 100
    k = rsv.ewm(com=m1-1, adjust=False).mean()
    d = k.ewm(com=m2-1, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j

def calc_boll(df, col='close', period=20, std_dev=2):
    """计算布林带"""
    mid = df[col].rolling(window=period).mean()
    std = df[col].rolling(window=period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower

def calc_volume_ratio(df, period=5):
    """计算量比"""
    avg_vol = df['volume'].rolling(window=period).mean()
    return df['volume'] / avg_vol

def calc_atr(df, period=14):
    """计算ATR（平均真实波幅）"""
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr

# ==================== 单只股票分析 ====================

def analyze_stock(code):
    """
    分析单只股票，返回技术指标和评分
    """
    try:
        # 获取历史K线（最近90天，用于计算指标）
        df = ak.stock_zh_a_hist(
            symbol=code,
            period='daily',
            start_date=(datetime.now() - timedelta(days=90)).strftime('%Y%m%d'),
            end_date=datetime.now().strftime('%Y%m%d'),
            adjust='qfq'
        )
        
        if df is None or len(df) < 30:
            return None
        
        # 获取最新实时行情
        spot = ak.stock_zh_a_spot_em()
        spot_row = spot[spot['代码'] == code]
        if spot_row.empty:
            return None
        
        # 提取数据
        close = df['收盘'].values
        high = df['最高'].values
        low = df['最低'].values
        volume = df['成交量'].values
        
        # 计算技术指标
        ma5 = calc_ma(df, '收盘', 5).iloc[-1]
        ma10 = calc_ma(df, '收盘', 10).iloc[-1]
        ma20 = calc_ma(df, '收盘', 20).iloc[-1]
        ma60 = calc_ma(df, '收盘', 60).iloc[-1] if len(df) >= 60 else ma20
        
        macd, macd_signal, macd_hist = calc_macd(df, '收盘')
        macd_val = macd.iloc[-1]
        macd_signal_val = macd_signal.iloc[-1]
        macd_hist_val = macd_hist.iloc[-1]
        
        rsi_val = calc_rsi(df, '收盘', 14).iloc[-1]
        
        k, d, j = calc_kdj(df)
        k_val = k.iloc[-1]
        d_val = d.iloc[-1]
        j_val = j.iloc[-1]
        
        boll_upper, boll_mid, boll_lower = calc_boll(df, '收盘')
        boll_upper_val = boll_upper.iloc[-1]
        boll_mid_val = boll_mid.iloc[-1]
        boll_lower_val = boll_lower.iloc[-1]
        
        vol_ratio = calc_volume_ratio(df, 5).iloc[-1]
        
        atr_val = calc_atr(df, 14).iloc[-1]
        
        # 最新价格和涨跌幅
        price = spot_row['最新价'].values[0]
        change_pct = spot_row['涨跌幅'].values[0]
        
        # 计算3日涨跌幅
        close_3d_ago = df['收盘'].iloc[-4] if len(df) >= 4 else df['收盘'].iloc[-1]
        change_3d = (float(price) / float(close_3d_ago) - 1) * 100 if close_3d_ago != 0 else 0
        
        # 当前收盘价
        current_close = df['收盘'].iloc[-1]
        
        # ========== 多因子评分（满分100分） ==========
        score = 0
        reasons = []
        
        # 因子1: 均线多头排列 (MA5 > MA10 > MA20) +20分
        if ma5 > ma10 > ma20:
            score += 20
            reasons.append("均线多头排列")
        elif ma5 > ma10:
            score += 10
            reasons.append("短期均线向上")
        
        # 因子2: MACD金叉 (MACD > Signal) +15分
        if macd_val > macd_signal_val:
            score += 15
            reasons.append("MACD金叉")
        elif macd_hist_val > 0:
            score += 8
            reasons.append("MACD红柱")
        
        # 因子3: RSI在50-70之间（强势非超买）+15分
        if 50 < rsi_val < 70:
            score += 15
            reasons.append(f"RSI={rsi_val:.1f}")
        elif 40 < rsi_val <= 50:
            score += 8
            reasons.append(f"RSI={rsi_val:.1f}")
        
        # 因子4: KDJ金叉 (K > D) +10分
        if k_val > d_val:
            score += 10
            reasons.append("KDJ金叉")
        
        # 因子5: 价格在布林带中轨上方 +10分
        if current_close > boll_mid_val:
            score += 10
            reasons.append("站上布林中轨")
        elif current_close > boll_lower_val:
            score += 5
            reasons.append("布林中轨下方")
        
        # 因子6: 量比 > 1.2（放量）+10分
        if vol_ratio > 1.2:
            score += 10
            reasons.append(f"量比{vol_ratio:.2f}")
        elif vol_ratio > 1.0:
            score += 5
            reasons.append(f"量比{vol_ratio:.2f}")
        
        # 因子7: 3日涨幅适中（0-8%，避免追高）+10分
        if 0 < change_3d < 8:
            score += 10
            reasons.append(f"3日涨{change_3d:.1f}%")
        elif -3 < change_3d <= 0:
            score += 5
            reasons.append(f"3日涨{change_3d:.1f}%")
        
        # 因子8: 当前涨跌幅为正 +5分
        if change_pct > 0:
            score += 5
            reasons.append(f"今日涨{change_pct:.2f}%")
        
        # 因子9: ATR波动适中（避免过度波动）+5分
        atr_pct = atr_val / current_close * 100 if current_close != 0 else 0
        if 1 < atr_pct < 5:
            score += 5
            reasons.append(f"波动{atr_pct:.1f}%")
        
        # 获取股票名称
        name = spot_row['名称'].values[0] if '名称' in spot_row.columns else code
        
        return {
            'code': code,
            'name': name,
            'price': float(price),
            'change_pct': float(change_pct),
            'score': score,
            'reasons': reasons,
            'ma5': float(ma5),
            'ma10': float(ma10),
            'ma20': float(ma20),
            'rsi': float(rsi_val),
            'kdj_k': float(k_val),
            'kdj_d': float(d_val),
            'vol_ratio': float(vol_ratio),
            'change_3d': float(change_3d),
            'atr_pct': float(atr_pct)
        }
        
    except Exception as e:
        if VERBOSE:
            print(f"  ⚠️ {code} 分析失败: {e}")
        return None

# ==================== 主筛选函数 ====================

def run_screener():
    """
    执行多因子筛选，返回TOP3
    """
    print(f"\n{'='*50}")
    print(f"📊 股票筛选系统 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    
    results = []
    total = len(STOCK_CODES)
    
    for i, code in enumerate(STOCK_CODES, 1):
        print(f"  分析 [{i}/{total}] {code}...", end=" ")
        result = analyze_stock(code)
        if result:
            results.append(result)
            print(f"✅ 得分: {result['score']}")
        else:
            print("❌ 失败")
        
        time.sleep(REQUEST_INTERVAL)
    
    if not results:
        print("\n❌ 未获取到任何有效数据，请检查网络或股票代码")
        return []
    
    # 按得分排序
    sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)
    
    # 输出结果
    print(f"\n{'='*50}")
    print(f"🏆 筛选结果 TOP3")
    print(f"{'='*50}")
    
    top3 = sorted_results[:3]
    for rank, stock in enumerate(top3, 1):
        print(f"\n【{rank}】 {stock['name']}({stock['code']})")
        print(f"   综合得分: {stock['score']}/100")
        print(f"   最新价: {stock['price']:.2f}  |  今日涨幅: {stock['change_pct']:.2f}%")
        print(f"   MA5: {stock['ma5']:.2f}  |  MA10: {stock['ma10']:.2f}  |  MA20: {stock['ma20']:.2f}")
        print(f"   RSI: {stock['rsi']:.1f}  |  KDJ-K: {stock['kdj_k']:.1f}  |  量比: {stock['vol_ratio']:.2f}")
        print(f"   推荐理由: {' + '.join(stock['reasons'][:4])}")
    
    # 显示完整排名
    if len(sorted_results) <= 20:
        print(f"\n{'='*50}")
        print("📋 完整排名")
        print(f"{'='*50}")
        for rank, stock in enumerate(sorted_results, 1):
            print(f"  {rank}. {stock['name']}({stock['code']}) - 得分: {stock['score']}")
    
    # 发送推送
    if top3:
        if FEISHU_WEBHOOK:
            send_feishu(top3)
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            send_telegram(top3)
    
    return top3

# ==================== 推送通知 ====================

def send_feishu(top3):
    """通过飞书机器人推送TOP3结果"""
    try:
        content = f"📈 **股票筛选结果**\n\n"
        content += f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        content += f"📊 股票池: {len(STOCK_CODES)}只\n\n"
        content += "**🏆 TOP3 推荐**\n"
        
        for i, stock in enumerate(top3, 1):
            content += f"\n{i}. **{stock['name']}** ({stock['code']})\n"
            content += f"   📊 综合得分: {stock['score']}/100\n"
            content += f"   💰 最新价: {stock['price']:.2f} | 涨幅: {stock['change_pct']:.2f}%\n"
            content += f"   📈 理由: {' + '.join(stock['reasons'][:3])}\n"
        
        data = {
            "msg_type": "text",
            "content": {"text": content}
        }
        
        response = requests.post(FEISHU_WEBHOOK, json=data, timeout=10)
        if response.status_code == 200:
            print("\n✅ 飞书推送成功")
        else:
            print(f"\n⚠️ 飞书推送失败: {response.status_code}")
            
    except Exception as e:
        print(f"\n⚠️ 飞书推送异常: {e}")

def send_telegram(top3):
    """通过Telegram Bot推送TOP3结果"""
    try:
        content = f"📈 *股票筛选结果*\n\n"
        content += f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        content += f"📊 股票池: {len(STOCK_CODES)}只\n\n"
        content += "*🏆 TOP3 推荐*\n"
        
        for i, stock in enumerate(top3, 1):
            content += f"\n{i}. *{stock['name']}* ({stock['code']})\n"
            content += f"   📊 综合得分: {stock['score']}/100\n"
            content += f"   💰 最新价: {stock['price']:.2f} | 涨幅: {stock['change_pct']:.2f}%\n"
            content += f"   📈 理由: {' + '.join(stock['reasons'][:3])}\n"
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": content,
            "parse_mode": "Markdown"
        }
        
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            print("\n✅ Telegram推送成功")
        else:
            print(f"\n⚠️ Telegram推送失败: {response.status_code}")
            
    except Exception as e:
        print(f"\n⚠️ Telegram推送异常: {e}")

# ==================== 定时任务 ====================

def schedule_loop(interval_minutes=5):
    """
    定时循环执行
    """
    import schedule
    
    print(f"🔄 定时模式已启动（每{interval_minutes}分钟执行一次）")
    print("   按 Ctrl+C 停止\n")
    
    # 立即执行一次
    run_screener()
    
    # 定时执行
    schedule.every(interval_minutes).minutes.do(run_screener)
    
    while True:
        schedule.run_pending()
        time.sleep(10)

# ==================== 命令行入口 ====================

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════╗
    ║    📈 股票多因子筛选系统 v2.0           ║
    ║    安卓 Termux 版                       ║
    ║    GitHub: stock_screener               ║
    ╚══════════════════════════════════════════╝
    """)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--schedule":
            interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            schedule_loop(interval)
        elif sys.argv[1] == "--help":
            print("用法:")
            print("  python app.py          # 单次运行")
            print("  python app.py --schedule [分钟]  # 定时运行")
            print("  python app.py --help   # 显示帮助")
    else:
        run_screener()
        print("\n✅ 筛选完成！")
        print("💡 提示: 使用 'python app.py --schedule 5' 启动定时模式（每5分钟）")
