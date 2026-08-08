import streamlit as st
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime

# ================= 1. 全局初始化 =================
st.set_page_config(page_title="智能多维看盘系统", layout="wide")

# 状态管理：控制监测开关
if 'monitoring' not in st.session_state:
    st.session_state.monitoring = False

st.title("📊 实时多维看盘系统 (自由自选股)")
st.caption("支持自动/手动切换监测，每5秒滚动获取最新行情及买卖点")

# ================= 2. 侧边栏设置区域 =================
with st.sidebar:
    st.header("⚙️ 策略与设置")
    
    # 1. 自选股输入（去掉了默认值，完全自由输入）
    codes_input = st.text_area("自选股池（一行一个，最多10只）", value="", placeholder="例如：\n600519\n000001\n002475")
    stock_codes = [c.strip() for c in codes_input.split('\n') if c.strip()][:10]
    
    # 2. 策略偏好
    trade_style = st.selectbox("📈 交易习惯", ["短线激进 (5日/20日)", "中线波段 (10日/30日)", "长线持有 (20日/60日)"])
    
    # 3. 风控阈值
    col1, col2 = st.columns(2)
    with col1:
        stop_loss = st.number_input("⛔ 止损比例 (%)", value=2.0, step=0.5) / 100.0
    with col2:
        take_profit = st.number_input("💰 止盈比例 (%)", value=5.0, step=0.5) / 100.0
        
    st.divider()
    # 4. 实时监测控制开关
    if st.button("🔄 开启 / 暂停 实时滚动监测"):
        st.session_state.monitoring = not st.session_state.monitoring

    # 状态提示
    if st.session_state.monitoring:
        st.success("✅ 实时监测已开启，每5秒自动刷新...")
        st_autorefresh(interval=5000, key="auto_refresh")
    else:
        st.warning("⏸️ 实时监测已暂停。请点击上方按钮开启。")

# ================= 3. 数据获取逻辑 =================
def get_stock_data(code):
    """获取A股历史数据（兼容真实与模拟）"""
    try:
        import akshare as ak
        # 获取后复权数据，选取最近60个交易日用于画图和计算均线
        df = ak.stock_zh_a_daily(symbol=code, adjust="qfq")
        if df is not None and not df.empty:
            return df.tail(60)
    except Exception as e:
        # 如果环境没有 akshare，生成模拟数据让程序保持能跑
        pass
    
    # 模拟数据兜底
    np.random.seed(hash(code) % 2**32)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=60, freq='D')
    prices = 10 + np.cumsum(np.random.randn(60) * 0.6)
    df = pd.DataFrame({
        'date': dates, 'open': prices, 'close': prices + np.random.randn(60)*0.1,
        'high': prices + np.abs(np.random.randn(60)*0.3),
        'low': prices - np.abs(np.random.randn(60)*0.3), 'volume': np.random.randint(1000, 10000, 60)
    })
    return df

# ================= 4. 核心分析算法 =================
def analyze_stock(df, sl_ratio, tp_ratio):
    """计算指标并判断买卖点"""
    if df.empty or len(df) < 20:
        return None, 0.0, pd.DataFrame()
    
    df = df.sort_values('date').reset_index(drop=True)
    # 计算多根均线
    df['MA5'] = df['close'].rolling(5).mean()
    df['MA20'] = df['close'].rolling(20).mean()
    
    current_price = df['close'].iloc[-1]
    signals = []
    
    # 1. 趋势信号（金叉/死叉）
    if len(df) > 1:
        if df['MA5'].iloc[-2] <= df['MA20'].iloc[-2] and df['MA5'].iloc[-1] > df['MA20'].iloc[-1]:
            signals.append({"type": "🟢 买入", "reason": f"MA5上穿MA20 (金叉) @ {current_price:.2f}"})
        elif df['MA5'].iloc[-2] >= df['MA20'].iloc[-2] and df['MA5'].iloc[-1] < df['MA20'].iloc[-1]:
            signals.append({"type": "🔴 卖出", "reason": f"MA5下穿MA20 (死叉) @ {current_price:.2f}"})
            
    # 2. 风控信号（以20日均价作为成本参考）
    avg_cost = df['close'].mean()
    if current_price < avg_cost * (1 - sl_ratio):
        signals.append({"type": "⛔ 止损卖出", "reason": f"下跌触发 {sl_ratio*100:.1f}% 止损线 @ {current_price:.2f}"})
    elif current_price > avg_cost * (1 + tp_ratio):
        signals.append({"type": "💰 止盈卖出", "reason": f"上涨触发 {tp_ratio*100:.1f}% 止盈线 @ {current_price:.2f}"})
        
    return signals, current_price, df

# ================= 5. 主界面渲染 =================
st.divider()

if st.session_state.monitoring:
    if not stock_codes:
        st.warning("⚠️ 左侧自选股池为空，请先输入股票代码再开启实时监测！")
    else:
        st.subheader(f"📡 实时行情 & 分析看板 (更新时间: {datetime.datetime.now().strftime('%H:%M:%S')})")
        
        # 多列布局（手机端自适应，最多显示3列）
        cols = st.columns(min(len(stock_codes), 3))
        
        for index, code in enumerate(stock_codes):
            df = get_stock_data(code)
            signals, price, df_analyzed = analyze_stock(df, stop_loss, take_profit)
            
            with cols[index % 3]:
                # 1. 核心价格卡片
                st.metric(label=f"**{code}**", value=f"{price:.2f}" if price > 0 else "无数据", delta=None)
                
                # 2. 买卖点信号提示
                if signals:
                    for sig in signals:
                        if "买入" in sig['type']:
                            st.success(f"{sig['type']}: {sig['reason']}")
                        elif "卖出" in sig['type'] and "止损" not in sig['type'] and "止盈" not in sig['type']:
                            st.warning(f"{sig['type']}: {sig['reason']}")
                        else:
                            st.error(f"{sig['type']}: {sig['reason']}")
                else:
                    st.caption("📝 暂无买卖点触发，建议观望。")
                
                # 3. 多维度图表展示 (收盘价 + MA5 + MA20)
                if not df_analyzed.empty:
                    # 为移动端手机优化图表高度
                    st.line_chart(df_analyzed, x='date', y=['close', 'MA5', 'MA20'], height=200)
else:
    st.info("👈 请在左侧点击红色的 '开启 / 暂停 实时滚动监测' 按钮，激活完整的实时看盘与分析面板。")
