import streamlit as st
import akshare as ak
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="多维度看盘系统", layout="wide")
st.title("📊 多维分析看盘（支持10只自选股）")

# ---- 侧边栏 ----
with st.sidebar:
    st.header("📋 自选股池（最多10只）")
    stock_input = st.text_area(
        "输入股票代码，一行一个",
        "000001\n002460\n600519",
        height=150
    )
    stock_list = [s.strip() for s in stock_input.split("\n") if s.strip()][:10]
    st.caption(f"当前监测 {len(stock_list)} 只")

    st.header("⚙️ 分析设置")
    profile = st.selectbox("交易习惯", ["短线激进", "中线稳健", "长线价值"])
    # 根据习惯设定默认止损止盈
    if profile == "短线激进":
        default_stop, default_take = 0.02, 0.05
    elif profile == "中线稳健":
        default_stop, default_take = 0.05, 0.15
    else:
        default_stop, default_take = 0.10, 0.30
    stop_loss = st.number_input("止损比例", value=default_stop*100, format="%.1f") / 100
    take_profit = st.number_input("止盈比例", value=default_take*100, format="%.1f") / 100

    run_btn = st.button("🚀 开始多维分析", type="primary")

# ---- 核心分析函数 ----
def fetch_multi_dim_data(code, profile):
    """获取并计算单个股票的多维数据，返回评分字典"""
    result = {
        "code": code,
        "name": code,  # 后面尝试获取名称
        "price": None,
        "dim_scores": {},
        "total_score": 0,
        "advice": "观望",
        "signals": [],
        "stop_loss_price": None,
        "take_profit_price": None,
        "error": None
    }
    try:
        # ---- 1. 获取实时行情与盘口数据 ----
        # 实时分时数据（最近1分钟）
        spot_df = ak.stock_zh_a_spot_em()
        spot_row = spot_df[spot_df['代码'] == code]
        if spot_row.empty:
            raise ValueError("未找到该股票")
        name = spot_row.iloc[0]['名称']
        price = float(spot_row.iloc[0]['最新价'])
        result["name"] = name
        result["price"] = price

        # 量比、换手率等
        volume_ratio = float(spot_row.iloc[0]['量比'])
        turnover = float(spot_row.iloc[0]['换手率'])

        # 资金流向（主力净流入，需要单独接口）
        try:
            fund_df = ak.stock_individual_fund_flow(stock=code, market="sh" if code.startswith("6") else "sz")
            main_net = fund_df.iloc[-1]['主力净流入-净额'] if not fund_df.empty else 0
        except:
            main_net = 0

        # ---- 2. 技术面数据（根据画像选择周期）----
        if profile == "短线激进":
            period = "60"
            ma_short, ma_long = 5, 20
        elif profile == "中线稳健":
            period = "daily"
            ma_short, ma_long = 10, 60
        else:
            period = "weekly"
            ma_short, ma_long = 10, 30

        if period == "60":
            df = ak.stock_zh_a_hist_min_em(symbol=code, period='60', adjust='qfq')
        elif period == "weekly":
            df = ak.stock_zh_a_hist(symbol=code, period='weekly', adjust='qfq')
        else:
            df = ak.stock_zh_a_hist(symbol=code, period='daily', adjust='qfq')

        df.rename(columns={'日期':'date','开盘':'open','收盘':'close','最高':'high','最低':'low','成交量':'volume'}, inplace=True)
        df['date'] = pd.to_datetime(df['date'])
        df.sort_values('date', inplace=True)
        df.reset_index(drop=True, inplace=True)

        # 计算常用指标
        df['MA_short'] = ta.sma(df['close'], ma_short)
        df['MA_long'] = ta.sma(df['close'], ma_long)
        df['RSI'] = ta.rsi(df['close'], length=14)
        macd = ta.macd(df['close'])
        df = pd.concat([df, macd], axis=1)
        bb = ta.bbands(df['close'], length=20, std=2)
        df = pd.concat([df, bb], axis=1)
        # 布林带位置
        df['BB_position'] = (df['close'] - df.iloc[:, bb.columns.get_loc('BBL_20_2.0')]) / (df.iloc[:, bb.columns.get_loc('BBU_20_2.0')] - df.iloc[:, bb.columns.get_loc('BBL_20_2.0')])

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # ---- 3. 基本面（静态估值）----
        try:
            fin_df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
            # 简单取最新的净利润增长率和PE
            net_profit_growth = float(fin_df.iloc[-1]['净利润同比增长率']) if '净利润同比增长率' in fin_df.columns else None
        except:
            net_profit_growth = None

        # PE、PB
        pe = float(spot_row.iloc[0]['市盈率-动态']) if '市盈率-动态' in spot_row.columns else None
        pb = float(spot_row.iloc[0]['市净率']) if '市净率' in spot_row.columns else None

        # ---- 4. 筹码结构（简化：用获利比例估算）----
        # 无免费精确筹码接口，用近期高低点近似
        high_60 = df['high'].tail(60).max()
        low_60 = df['low'].tail(60).min()
        profit_ratio = (price - low_60) / (high_60 - low_60) * 100 if high_60 != low_60 else 50

        # ---- 5. 情绪消息（用融资融券和公告）----
        # 融资融券
        try:
            margin_df = ak.stock_margin_detail_sse(date=datetime.now().strftime("%Y%m%d"))
            # 因为接口变动，暂时置0
            margin_change = 0
        except:
            margin_change = 0

        # ---- 多维度评分（0-100）----
        scores = {}
        # 1. 盘面微观 (30分)
        micro_score = 15  # 基础
        if price > float(spot_row.iloc[0]['今开']) and volume_ratio > 1.2:
            micro_score += 5
        if main_net > 0:
            micro_score += 5
        if volume_ratio > 1.8:
            micro_score += 3
        micro_score = min(micro_score, 30)
        scores["盘面微观"] = micro_score

        # 2. 技术面 (30分)
        tech_score = 15
        # 均线多头排列
        if latest['MA_short'] > latest['MA_long'] and df['MA_short'].iloc[-5] > df['MA_long'].iloc[-5]:
            tech_score += 5
        # MACD 金叉/红柱
        if latest['MACD_12_26_9'] > latest['MACDs_12_26_9']:
            tech_score += 3
        # RSI 健康区间(30-70)
        if 30 < latest['RSI'] < 70:
            tech_score += 3
        # 布林带位置（中轨上方）
        bb_pos = latest['BB_position']
        if 0.3 < bb_pos < 0.7:
            tech_score += 4
        elif bb_pos > 0.7 and latest['close'] > latest['MA_short']:
            tech_score += 2  # 强势但超买
        tech_score = min(tech_score, 30)
        scores["技术面"] = tech_score

        # 3. 筹码资金 (20分)
        fund_score = 10
        # 获利比例较高且主力流入
        if 30 < profit_ratio < 80 and main_net > 0:
            fund_score += 5
        if main_net > 0 and abs(main_net) > 100000:  # 净流入大于一定值
            fund_score += 3
        fund_score = min(fund_score, 20)
        scores["筹码资金"] = fund_score

        # 4. 基本面 (10分)
        basic_score = 5
        if pe and pe > 0 and pe < 30:
            basic_score += 2
        if net_profit_growth and net_profit_growth > 20:
            basic_score += 3
        scores["基本面"] = basic_score

        # 5. 情绪消息 (10分)
        senti_score = 5
        if margin_change > 0:
            senti_score += 2
        # 换手率适中
        if 1 < turnover < 5:
            senti_score += 3
        scores["情绪消息"] = senti_score

        total = sum(scores.values())
        result["dim_scores"] = scores
        result["total_score"] = total

        # 综合建议
        if total >= 85:
            advice = "🟢 强势做多"
        elif total >= 70:
            advice = "🟡 偏多关注"
        elif total >= 50:
            advice = "⚪ 中性观望"
        else:
            advice = "🔴 风险回避"
        result["advice"] = advice

        # 具体买卖信号收集
        signals = []
        if latest['MA_short'] > latest['MA_long'] and prev['MA_short'] <= prev['MA_long']:
            signals.append("均线金叉")
        if latest['RSI'] > 30 and df['RSI'].iloc[-2] <= 30:
            signals.append("RSI超卖反弹")
        if latest['MACD_12_26_9'] > latest['MACDs_12_26_9'] and prev['MACD_12_26_9'] <= prev['MACDs_12_26_9']:
            signals.append("MACD金叉")
        if latest['close'] < latest.iloc[:, bb.columns.get_loc('BBL_20_2.0')]:
            signals.append("触及布林下轨")
        if signals:
            result["signals"] = signals
            result["stop_loss_price"] = price * (1 - stop_loss)
            result["take_profit_price"] = price * (1 + take_profit)

        return result
    except Exception as e:
        result["error"] = str(e)
        return result

# ---- 运行分析 ----
if run_btn:
    if not stock_list:
        st.warning("请输入至少一个股票代码")
    else:
        with st.spinner("正在多维分析中，请稍候..."):
            results = []
            for code in stock_list:
                res = fetch_multi_dim_data(code, profile)
                results.append(res)

        # 展示结果
        st.subheader(f"📈 综合看盘结果（{profile}）")

        # 表格汇总
        summary_data = []
        for r in results:
            summary_data.append({
                "股票": f"{r['name']}({r['code']})",
                "最新价": f"{r['price']:.2f}" if r['price'] else "获取失败",
                "盘面": r['dim_scores'].get('盘面微观', 0) if not r['error'] else "-",
                "技术": r['dim_scores'].get('技术面', 0) if not r['error'] else "-",
                "筹码资金": r['dim_scores'].get('筹码资金', 0) if not r['error'] else "-",
                "基本面": r['dim_scores'].get('基本面', 0) if not r['error'] else "-",
                "情绪": r['dim_scores'].get('情绪消息', 0) if not r['error'] else "-",
                "总分": r['total_score'] if not r['error'] else "-",
                "建议": r['advice']
            })
        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, use_container_width=True)

        # 详细展开每只股票
        for i, r in enumerate(results):
            if r['error']:
                st.warning(f"❌ {r['code']} 获取失败：{r['error']}")
                continue
            with st.expander(f"📌 {r['name']}({r['code']}) — {r['advice']}  (总分: {r['total_score']})"):
                col1, col2 = st.columns(2)
                col1.metric("最新价", f"{r['price']:.2f} 元")
                col1.write("**各维度得分**")
                for dim, score in r['dim_scores'].items():
                    col1.progress(score/100, text=f"{dim}: {score}/100")
                if r['signals']:
                    col2.write("**触发信号**")
                    for sig in r['signals']:
                        col2.success(sig)
                    col2.write(f"止损价: {r['stop_loss_price']:.2f}")
                    col2.write(f"止盈价: {r['take_profit_price']:.2f}")

        st.caption("免责声明：基于公开数据与多维模型生成，仅供学习参考，不构成投资建议。")
else:
    st.info("👈 输入自选股代码，点击开始分析，支持最多10只同时监测。")
