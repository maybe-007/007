#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票多因子筛选系统 - Streamlit Web版
支持1-20只股票，多因子打分筛选TOP3
数据源：AKShare
GitHub：https://github.com/你的用户名/007
"""

import streamlit as st
import akshare as ak
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="股票多因子筛选系统",
    page_icon="📈",
    layout="wide"
)

# ==================== 默认股票池 ====================
DEFAULT_CODES = [
    '000001', '000002', '000858', '002415', '002594',
    '300750', '600036', '600519', '600900', '601318',
    '601398', '601857', '601166', '601288', '601328',
    '600276', '600030', '601688', '600887', '603288'
]

# ==================== 技术指标计算 ====================

def calc_ma(df, col='close', period=5):
    return df[col].rolling(window=period).mean()

def calc_macd(df, col='close', fast=12, slow=26, signal=9):
    exp_fast = df[col].ewm(span=fast, adjust=False).mean()
    exp_slow = df[col].ewm(span=slow, adjust=False).mean()
    macd = exp_fast - exp_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - macd_signal
    return macd, macd_signal, macd_hist

def calc_rsi(df, col='close', period=14):
    delta = df[col].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_kdj(df, n=9, m1=3, m2=3):
    low_min = df['low'].rolling(window=n).min()
    high_max = df['high'].rolling(window=n).max()
    rsv = (df['close'] - low_min) / (high_max - low_min) * 100
    k = rsv.ewm(com=m1-1, adjust=False).mean()
    d = k.ewm(com=m2-1, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j

def calc_boll(df, col='close', period=20, std_dev=2):
    mid = df[col].rolling(window=period).mean()
    std = df[col].rolling(window=period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower

def calc_volume_ratio(df, period=5):
    avg_vol = df['volume'].rolling(window=period).mean()
    return df['volume'] / avg_vol

def calc_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr

# ==================== 单只股票分析 ====================

def analyze_stock(code):
    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period='daily',
            start_date=(datetime.now() - timedelta(days=90)).strftime('%Y%m%d'),
            end_date=datetime.now().strftime('%Y%m%d'),
            adjust='qfq'
        )
        
        if df is None or len(df) < 30:
            return None
        
        spot = ak.stock_zh_a_spot_em()
        spot_row = spot[spot['代码'] == code]
        if spot_row.empty:
            return None
        
        ma5 = calc_ma(df, '收盘', 5).iloc[-1]
        ma10 = calc_ma(df, '收盘', 10).iloc[-1]
        ma20 = calc_ma(df, '收盘', 20).iloc[-1]
        
        macd, macd_signal, macd_hist = calc_macd(df, '收盘')
        macd_val = macd.iloc[-1]
        macd_signal_val = macd_signal.iloc[-1]
        macd_hist_val = macd_hist.iloc[-1]
        
        rsi_val = calc_rsi(df, '收盘', 14).iloc[-1]
        k, d, j = calc_kdj(df)
        k_val = k.iloc[-1]
        d_val = d.iloc[-1]
        
        boll_upper, boll_mid, boll_lower = calc_boll(df, '收盘')
        boll_mid_val = boll_mid.iloc[-1]
        boll_lower_val = boll_lower.iloc[-1]
        
        vol_ratio = calc_volume_ratio(df, 5).iloc[-1]
        atr_val = calc_atr(df, 14).iloc[-1]
        
        price = spot_row['最新价'].values[0]
        change_pct = spot_row['涨跌幅'].values[0]
        
        close_3d_ago = df['收盘'].iloc[-4] if len(df) >= 4 else df['收盘'].iloc[-1]
        change_3d = (float(price) / float(close_3d_ago) - 1) * 100 if close_3d_ago != 0 else 0
        current_close = df['收盘'].iloc[-1]
        
        # ========== 多因子评分 ==========
        score = 0
        reasons = []
        
        if ma5 > ma10 > ma20:
            score += 20
            reasons.append("均线多头排列")
        elif ma5 > ma10:
            score += 10
            reasons.append("短期均线向上")
        
        if macd_val > macd_signal_val:
            score += 15
            reasons.append("MACD金叉")
        elif macd_hist_val > 0:
            score += 8
            reasons.append("MACD红柱")
        
        if 50 < rsi_val < 70:
            score += 15
            reasons.append(f"RSI={rsi_val:.1f}")
        elif 40 < rsi_val <= 50:
            score += 8
            reasons.append(f"RSI={rsi_val:.1f}")
        
        if k_val > d_val:
            score += 10
            reasons.append("KDJ金叉")
        
        if current_close > boll_mid_val:
            score += 10
            reasons.append("站上布林中轨")
        elif current_close > boll_lower_val:
            score += 5
            reasons.append("布林中轨下方")
        
        if vol_ratio > 1.2:
            score += 10
            reasons.append(f"量比{vol_ratio:.2f}")
        elif vol_ratio > 1.0:
            score += 5
            reasons.append(f"量比{vol_ratio:.2f}")
        
        if 0 < change_3d < 8:
            score += 10
            reasons.append(f"3日涨{change_3d:.1f}%")
        elif -3 < change_3d <= 0:
            score += 5
            reasons.append(f"3日涨{change_3d:.1f}%")
        
        if change_pct > 0:
            score += 5
            reasons.append(f"今日涨{change_pct:.2f}%")
        
        atr_pct = atr_val / current_close * 100 if current_close != 0 else 0
        if 1 < atr_pct < 5:
            score += 5
            reasons.append(f"波动{atr_pct:.1f}%")
        
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
        return None

# ==================== 主筛选函数 ====================

def run_screener(codes):
    results = []
    total = len(codes)
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, code in enumerate(codes):
        status_text.text(f"正在分析 [{i+1}/{total}] {code}...")
        result = analyze_stock(code)
        if result:
            results.append(result)
        time.sleep(0.3)
        progress_bar.progress((i + 1) / total)
    
    status_text.text("分析完成！")
    return results

# ==================== Streamlit UI ====================

st.title("📈 股票多因子筛选系统")
st.markdown("---")

# 侧边栏配置
with st.sidebar:
    st.header("⚙️ 配置")
    
    stock_input = st.text_area(
        "输入股票代码（每行一个，最多20只）",
        value="\n".join(DEFAULT_CODES),
        height=400
    )
    
    codes = [code.strip() for code in stock_input.split('\n') if code.strip()]
    
    if len(codes) > 20:
        st.error(f"⚠️ 最多支持20只，当前 {len(codes)} 只")
        codes = codes[:20]
    elif len(codes) == 0:
        st.error("⚠️ 请至少输入1只股票")
    
    st.info(f"📊 当前股票池：{len(codes)} 只")
    
    run_btn = st.button("🚀 开始筛选", type="primary", use_container_width=True)

# 主区域
if run_btn and codes:
    with st.spinner("正在获取数据并分析..."):
        results = run_screener(codes)
    
    if not results:
        st.error("❌ 未获取到任何有效数据，请检查网络或股票代码")
    else:
        # 按得分排序
        sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)
        top3 = sorted_results[:3]
        
        # ===== 显示TOP3 =====
        st.subheader("🏆 TOP3 推荐")
        
        cols = st.columns(3)
        for idx, stock in enumerate(top3):
            with cols[idx]:
                color = "🟢" if stock['change_pct'] > 0 else "🔴"
                st.markdown(f"""
                <div style="
                    background: {'#e8f5e9' if idx==0 else '#e3f2fd' if idx==1 else '#fff3e0'};
                    padding: 16px;
                    border-radius: 12px;
                    border: 1px solid #ddd;
                ">
                    <h3 style="margin:0">#{idx+1} {stock['name']}</h3>
                    <p style="margin:4px 0;color:#666;">{stock['code']}</p>
                    <h2>{stock['score']}<span style="font-size:16px;color:#999;">/100</span></h2>
                    <p style="margin:4px 0;">
                        最新价：<b>{stock['price']:.2f}</b>
                        {color} {stock['change_pct']:+.2f}%
                    </p>
                    <p style="margin:4px 0;font-size:14px;">
                        📊 {stock['reasons'][0] if stock['reasons'] else ''}
                    </p>
                </div>
                """, unsafe_allow_html=True)
        
        # ===== 显示完整排名表格 =====
        st.subheader("📋 完整排名")
        
        df_display = pd.DataFrame(sorted_results)
        df_display = df_display[[
            'code', 'name', 'score', 'price', 'change_pct', 
            'ma5', 'ma10', 'ma20', 'rsi', 'vol_ratio'
        ]]
        df_display.columns = [
            '代码', '名称', '综合得分', '最新价', '涨幅%',
            'MA5', 'MA10', 'MA20', 'RSI', '量比'
        ]
        df_display['涨幅%'] = df_display['涨幅%'].map(lambda x: f"{x:+.2f}%")
        
        # 高亮TOP3
        def highlight_top3(row):
            idx = row.name
            if idx == 0:
                return ['background-color: #e8f5e9'] * len(row)
            elif idx == 1:
                return ['background-color: #e3f2fd'] * len(row)
            elif idx == 2:
                return ['background-color: #fff3e0'] * len(row)
            return [''] * len(row)
        
        st.dataframe(
            df_display.style.apply(highlight_top3, axis=1),
            use_container_width=True,
            hide_index=True,
            height=400
        )
        
        # ===== 导出结果 =====
        st.download_button(
            label="📥 下载结果 CSV",
            data=df_display.to_csv(index=False),
            file_name=f"stock_screener_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

elif not run_btn:
    st.info("👈 左侧输入股票代码，点击「开始筛选」运行")

st.markdown("---")
st.caption("⚠️ 本程序仅供学习研究，不构成投资建议。数据来自 AKShare，实时性约5-10分钟延迟。")
