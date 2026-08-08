import streamlit as st
import akshare as ak
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timedelta
import time
import random

# ---- 页面配置（深色护眼）----
st.set_page_config(page_title="六维看盘·多股监测", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    .main-header { color: #00FF88; font-size: 1.8rem; font-weight: bold; }
    .metric-box { background: #1A1C23; border-radius: 12px; padding: 10px; margin: 5px 0; 
                  border-left: 4px solid #00FF88; }
    .metric-box.sell { border-left-color: #FF5555; }
    .signal-badge { background: #00FF8830; color: #00FF88; padding: 2px 8px; border-radius: 10px; font-size: 0.8rem; }
    .signal-badge.warn { background: #FFAA0030; color: #FFAA00; }
    .signal-badge.danger { background: #FF555530; color: #FF5555; }
    .stProgress > div > div { background: linear-gradient(90deg, #00FF88, #00AAFF); }
    .refresh-timer { font-size: 0.8rem; color: #888; text-align: right; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">📊 六维滚动看盘 · 10股同屏监测</div>', unsafe_allow_html=True)

# ---- 侧边栏设置 ----
with st.sidebar:
    st.header("⚙️ 控制面板")
    stock_input = st.text_area("股票代码（一行一个，最多10只）", 
                               "000001\n002460\n600519\n300750\n000858", height=130)
    stock_list = [s.strip() for s in stock_input.split("\n") if s.strip()][:10]

    profile = st.selectbox("交易风格", ["短线激进", "中线波段", "长线价值"], index=0)
    
    # 刷新间隔（最低60秒，防封禁）
    refresh_sec = st.slider("数据刷新间隔（秒）", 60, 300, 90, 30, help="≥60秒可避免被数据源封IP")
    
    # 出击信号阈值
    confidence = st.slider("出击信号强度阈值（总分）", 60, 95, 75, 5, help="总分超过此值才提示出击")
    
    # 止损方式
    stop_method = st.selectbox("止损参考", ["起动阳线最低价", "20日均线", "布林下轨"])

    # 展示宏观预警摘要
    with st.expander("📡 宏观流动性雷达"):
        macro_placeholder = st.empty()

st.caption("💡 点击“开始监测”后，系统将自动每{}秒刷新一次（含随机延迟），长期运行时请保持页面开启。".format(refresh_sec))

# ---- 数据获取与六维引擎 ----
@st.cache_data(ttl=300)
def get_macro_liquidity():
    """宏观流动性（缓存5分钟）"""
    try:
        # 使用Shibor隔夜利率 + 近期IPO数量
        shibor = ak.macro_china_shibor_all()
        on_rate = float(shibor.iloc[-1]['ON']) if not shibor.empty else 1.6
        ipo = ak.stock_new_ipo_cninfo()
        recent_ipo = ipo[ipo['上网发行日期'] > (datetime.now()-timedelta(7)).strftime('%Y%m%d')].shape[0] if not ipo.empty else 0
        if recent_ipo > 5 or on_rate > 2.0:
            status = "⚠️ 资金虹吸风险，注意仓位"
        else:
            status = "✅ 流动性充裕"
        return {"shibor_on": on_rate, "recent_ipo": recent_ipo, "status": status}
    except:
        return {"shibor_on": "N/A", "recent_ipo": "N/A", "status": "数据获取失败"}

@st.cache_data(ttl=600)
def get_financial_health(code):
    """三层次财务体检（缓存10分钟）"""
    try:
        fin = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
        if fin.empty:
            return {"生存": "?", "质量": "?", "成长": "?"}, {}
        row = fin.iloc[-1]
        # 生存：流动比率
        cur_r = float(row.get('流动比率', 2))
        quick_r = float(row.get('速动比率', 1))
        survive = "✅" if cur_r > 1 and quick_r > 0.5 else "❌"
        # 质量：经营现金流/净利润
        op_cash = float(row.get('经营活动产生的现金流量净额', 0))
        net_p = float(row.get('净利润', 1))
        quality = "✅" if (op_cash / net_p > 0.5 if net_p else True) else "⚠️"
        # 成长：营收增速
        rev_g = float(row.get('营业总收入同比增长率', 0))
        growth = "✅" if rev_g > 10 else ("📉" if rev_g < 0 else "→")
        details = {"流动比率": cur_r, "现金流/净利润": op_cash/net_p if net_p else np.nan, "营收增速": rev_g}
        return {"生存": survive, "质量": quality, "成长": growth}, details
    except:
        return {"生存": "?", "质量": "?", "成长": "?"}, {}

def classify_valuation(code, price, pe, pb):
    """分类估值定价"""
    # 简单分类逻辑（实际可扩展行业数据）
    try:
        industry_pe = 25  # 暂时设定为全市场中位数，后续可替换
        if pe and pb and pe < 15 and pb < 1.5:
            cat = "价值股"
            comment = f"PE {pe:.1f} ({'低估' if pe < industry_pe*0.7 else '合理'})"
        elif pe and pe < 30 and pe > 0:
            # 尝试获取净利润增速
            fin, _ = get_financial_health(code)
            growth_rate = fin.get('成长', 0)
            if isinstance(growth_rate, str): growth_rate = 15
            peg = pe / growth_rate if growth_rate else 999
            cat = "成长股"
            comment = f"PEG {peg:.2f} ({'低估' if peg < 1 else '高估'})"
        else:
            cat = "周期股"
            comment = f"PB {pb:.1f} (结合库存周期判断)"
        return cat, comment
    except:
        return "无法分类", ""

def analyze_single_stock(code, profile, stop_method, confidence):
    """六维评分主函数"""
    result = {"code": code, "name": code, "price": None, "advice": "数据异常", "total": 0, "signals": []}
    try:
        # ---- 实时行情 ----
        spot = ak.stock_zh_a_spot_em()
        row = spot[spot['代码'] == code]
        if row.empty:
            raise ValueError("未找到代码")
        price = float(row.iloc[0]['最新价'])
        name = row.iloc[0]['名称']
        open_price = float(row.iloc[0]['今开'])
        volume_ratio = float(row.iloc[0]['量比'])
        turnover = float(row.iloc[0]['换手率'])
        pe = float(row.iloc[0].get('市盈率-动态', 0)) or None
        pb = float(row.iloc[0].get('市净率', 0)) or None
        result.update({"name": name, "price": price})

        # 主力资金流向
        try:
            market = "sh" if code.startswith("6") else "sz"
            fund_df = ak.stock_individual_fund_flow(stock=code, market=market)
            main_net = fund_df.iloc[-1]['主力净流入-净额'] if not fund_df.empty else 0
        except:
            main_net = 0

        # ---- 宏观维度（15分） ----
        macro = get_macro_liquidity()
        macro_score = 15 if "充裕" in macro['status'] else 8
        macro_warn = macro['status']

        # ---- 盘口微观（15分） ----
        micro_score = 8
        if price > open_price and volume_ratio > 1.2:
            micro_score += 3
        if volume_ratio > 1.8:
            micro_score += 2
        micro_score = min(micro_score, 15)

        # ---- 技术形态（25分） ----
        # 根据风格选K线周期
        if profile == "短线激进":
            period, ma_s, ma_l = "60", 5, 20
        elif profile == "中线波段":
            period, ma_s, ma_l = "daily", 10, 60
        else:
            period, ma_s, ma_l = "weekly", 10, 30

        if period == "60":
            df = ak.stock_zh_a_hist_min_em(symbol=code, period='60', adjust='qfq')
        elif period == "weekly":
            df = ak.stock_zh_a_hist(symbol=code, period='weekly', adjust='qfq')
        else:
            df = ak.stock_zh_a_hist(symbol=code, period='daily', adjust='qfq')

        df.columns = [c.lower() for c in df.columns]
        df.rename(columns={'日期':'date','开盘':'open','收盘':'close','最高':'high','最低':'low','成交量':'volume'}, inplace=True)
        df['date'] = pd.to_datetime(df['date'])
        df.sort_values('date', inplace=True)
        df.dropna(subset=['close'], inplace=True)

        df['MA_short'] = ta.sma(df['close'], ma_s)
        df['MA_long'] = ta.sma(df['close'], ma_l)
        df['RSI'] = ta.rsi(df['close'], 14)
        macd = ta.macd(df['close'])
        df = pd.concat([df, macd], axis=1)
        bb = ta.bbands(df['close'], 20, 2)
        df = pd.concat([df, bb], axis=1)

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        tech_score = 12
        signals = []

        # 金叉
        if latest['MA_short'] > latest['MA_long'] and prev['MA_short'] <= prev['MA_long']:
            tech_score += 5
            signals.append("均线金叉")
        # MACD金叉
        if latest['MACD_12_26_9'] > latest['MACDs_12_26_9'] and prev['MACD_12_26_9'] <= prev['MACDs_12_26_9']:
            tech_score += 3
            signals.append("MACD金叉")
        # RSI健康
        rsi_now = latest['RSI']
        if 30 < rsi_now < 70:
            tech_score += 2
        # 布林下轨
        bb_low = df.iloc[:, bb.columns.get_loc('BBL_20_2.0')].iloc[-1]
        if latest['close'] < bb_low * 1.02:
            signals.append("触及布林下轨")
            tech_score += 2
        tech_score = min(tech_score, 25)

        # ---- 三层次财务（20分） ----
        health, _ = get_financial_health(code)
        fin_score = 10
        if health["生存"] == "✅": fin_score += 4
        if health["质量"] == "✅": fin_score += 3
        if health["成长"] == "✅": fin_score += 3
        result["health"] = health

        # ---- 估值定价（15分） ----
        cat, comment = classify_valuation(code, price, pe, pb)
        valu_score = 8
        if "低估" in comment: valu_score += 4
        if cat == "价值股": valu_score += 1
        result["valuation"] = f"{cat} | {comment}"

        # ---- 筹码情绪（10分） ----
        senti_score = 5
        if main_net > 0: senti_score += 2
        if 1 < volume_ratio < 5: senti_score += 3
        senti_score = min(senti_score, 10)

        # 综合总分
        dim_scores = {
            "宏观": macro_score,
            "盘口": micro_score,
            "技术": tech_score,
            "财务": fin_score,
            "估值": valu_score,
            "情绪": senti_score
        }
        total = sum(dim_scores.values())
        result["total"] = total
        result["dim_scores"] = dim_scores
        result["macro_warn"] = macro_warn

        # 三因子共振（技术≥20, 量比>1.5, 主力净流入）
        tech_ok = tech_score >= 20
        volume_ok = volume_ratio > 1.5
        fund_ok = main_net > 0
        if tech_ok and volume_ok and fund_ok:
            signals.append("🔥 三因子共振出击")
            result["advice"] = "🟢 高胜率买点"
        elif total >= confidence:
            result["advice"] = "🟡 偏多关注"
        elif total >= 45:
            result["advice"] = "⚪ 中性观望"
        else:
            result["advice"] = "🔴 风险回避"

        result["signals"] = signals

        # 止损/止盈计算
        if stop_method == "起动阳线最低价":
            # 简化：取最近一根成交量明显放大的阳线最低价
            large_vol = df[df['volume'] > df['volume'].rolling(5).mean() * 1.5]
            if not large_vol.empty:
                stop_price = large_vol.iloc[-1]['low']
            else:
                stop_price = latest['low']
        elif stop_method == "20日均线":
            stop_price = df['close'].rolling(20).mean().iloc[-1]
        else:
            stop_price = bb_low
        result["stop_loss"] = stop_price
        result["take_profit"] = price * 1.08  # 默认8%止盈

    except Exception as e:
        result["error"] = str(e)[:80]
    return result

# ---- 主界面操作 ----
if st.button("▶️ 开始监测（自动刷新）", use_container_width=True):
    if not stock_list:
        st.warning("请先输入股票代码")
    else:
        # 初始化会话状态
        if 'last_refresh' not in st.session_state:
            st.session_state.last_refresh = 0

        # 显示倒计时
        timer_placeholder = st.empty()
        main_view = st.empty()

        while True:
            now = datetime.now()
            # 控制刷新频率
            elapsed = (now - st.session_state.last_refresh).total_seconds() if st.session_state.last_refresh else 999
            if elapsed < refresh_sec:
                remaining = refresh_sec - elapsed
                timer_placeholder.info(f"⏳ 距离下次刷新还有 {int(remaining)} 秒（实际间隔≥{refresh_sec}秒，防封禁）")
                time.sleep(1)
                continue

            # 执行刷新
            st.session_state.last_refresh = now
            timer_placeholder.empty()
            
            with main_view.container():
                st.subheader(f"🔄 刷新时间：{now.strftime('%H:%M:%S')}  |  监控 {len(stock_list)} 只股票")
                
                # 宏观摘要
                macro_data = get_macro_liquidity()
                macro_placeholder.metric("宏观流动性", macro_data['status'], f"IPO: {macro_data['recent_ipo']}家 | Shibor: {macro_data['shibor_on']}")
                
                # 分析所有股票
                results = []
                for code in stock_list:
                    res = analyze_single_stock(code, profile, stop_method, confidence)
                    results.append(res)
                    # 微小延迟，避免请求过快
                    time.sleep(random.uniform(0.1, 0.3))
                
                # 10股雷达网格（自动适配横向滚动）
                cols = st.columns(min(len(results), 5))
                for i, res in enumerate(results):
                    col = cols[i % 5]
                    with col:
                        if res.get('error'):
                            st.error(f"{res['code']}\n{res['error']}")
                        else:
                            advice_color = "buy" if "买" in res['advice'] else ("sell" if "回避" in res['advice'] else "")
                            st.markdown(f"""
                            <div class="metric-box {'sell' if '回避' in res['advice'] else ''}">
                                <b>{res['name']}</b><br>
                                <span style="font-size:1.2em;">{res['price']:.2f}</span><br>
                                <span style="color:{'#00FF88' if '买' in res['advice'] else '#FFAA00'}">{res['advice']}</span><br>
                                <small>总分: {res['total']}</small>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # 点击展开详情
                            with st.expander(f"📌 {res['name']} 详情"):
                                col1, col2 = st.columns(2)
                                col1.write(f"**宏观**：{res['macro_warn']}")
                                col1.write(f"**估值**：{res['valuation']}")
                                col1.write("**财务体检**：" + " | ".join([f"{k}:{v}" for k,v in res.get('health', {}).items()]))
                                col2.write("**各维度得分**")
                                for dim, score in res.get('dim_scores', {}).items():
                                    col2.progress(score/100, text=f"{dim}: {score}")
                                if res['signals']:
                                    for sig in res['signals']:
                                        if "共振" in sig:
                                            col2.success(sig)
                                        else:
                                            col2.info(sig)
                                col2.metric("参考止损", f"{res['stop_loss']:.2f}")
                                col2.metric("参考止盈", f"{res['take_profit']:.2f}")

            # 等待下一次刷新（加入随机抖动）
            jitter = random.uniform(0, 10)
            time.sleep(refresh_sec + jitter)
            # 使用st.rerun刷新整个页面（更稳定）
            st.rerun()

else:
    st.info("👆 点击上方按钮启动六维实时监测，系统将按设定间隔自动刷新数据。")

st.markdown("---")
st.caption("⚠️ 免责声明：数据来源于公开接口，分析结果仅供学习研究，不构成投资建议。市场有风险，投资需谨慎。")
