import streamlit as st
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime

# ================= 配置全局设置 =================
st.set_page_config(layout="wide", page_title="智能多维看盘系统")

# 初始化 Session State
if 'monitoring' not in st.session_state:
    st.session_state.monitoring = False

st.title("📊 多维分析看盘 (实时滚动监测)")

# ================= 侧边栏设置区域 =================
with st.sidebar:
    st.header("⚙️ 策略设置")
    
    # 1. 股票代码池（去掉了默认的 value，改为空值，由用户自由输入）
    codes_input = st.text_area("自选股池（一行一个，最多10只）", value="", placeholder="例如：\n600519\n000001\n002475")
    # 处理输入，去除空行和空格
    stock_codes = [c.strip() for c in codes_input.split('\n') if c.strip()][:10]
    
    # 2. 交易习惯
    trade_style = st.selectbox("交易习惯", ["短线激进", "中线波段", "长线持有"])
    
    # 3. 风控设置
    col1, col2 = st.columns(2)
    with col1:
        stop_loss = st.number_input("止损比例 (%)", min_value=0.0, max_value=100.0, value=2.0, step=0.5) / 100.0
    with col2:
        take_profit = st.number_input("止盈比例 (%)", min_value=0.0, max_value=100.0, value=5.0, step=0.5) / 100.0
    
    st.divider()
    # 4. 启动 / 暂停 按钮
    if st.button("🔄 开始/暂停 实时滚动监测"):
        st.session_state.monitoring = not st.session_state.monitoring

    # 5. 实时状态显示
    if st.session_state.monitoring:
        st.success("✅ 实时监测已开启，数据将每5秒滚动更新...")
        st_autorefresh(interval=5000, key="auto_refresh")
    else:
        st.warning("⏸️ 当前监测已暂停。")

# ================= 核心数据与算法逻辑 =================

# 获取数据（兼容Akshare真实数据与模拟数据）
def get_data(code):
    try:
        import akshare as ak
        df = ak.stock_zh_a_daily(symbol=code, adjust="qfq")
        return df.tail(60) # 取最近60天做均线分析
    except ImportError:
        # 如果没安装akshare，生成模拟数据防止报错
        np.random.seed(int(code) if code.isdigit() else 0)
        dates = pd.date_range(end=pd.Timestamp.now(), periods=60, freq='D')
        prices = 10 + np.cumsum(np.random.randn(60) * 0.8)
        df = pd.DataFrame({
            'date': dates, 
            'close': prices + np.random.randn(60)*0.1,
        })
        return df
    except Exception as e:
        st.error(f"🚨 获取 {code} 数据失败: {e}")
        return pd.DataFrame()

# 分析买卖点算法
def analyze_strategy(df, sl_ratio, tp_ratio):
    if df.empty or len(df) < 20:
        return None, 0.0
    
    df = df.sort_values('date').reset_index(drop=True)
    df['MA5'] = df['close'].rolling(5).mean()
    df['MA20'] = df['close'].rolling(20).mean()
    
    current_price = df['close'].iloc[-1]
    
    prev_ma5 = df['MA5'].iloc[-2] if len(df) > 1 else 0
    prev_ma20 = df['MA20'].iloc[-2] if len(df) > 1 else 0
    curr_ma5 = df['MA5'].iloc[-1]
    curr_ma20 = df['MA20'].iloc[-1]
    
    signals = []
    # 1. 策略信号
    if prev_ma5 <= prev_ma20 and curr_ma5 > curr_ma20:
        signals.append({"type": "买入", "reason": "MA5上穿MA20 (金叉)", "price": current_price})
    elif prev_ma5 >= prev_ma20 and curr_ma5 < curr_ma20:
        signals.append({"type": "卖出", "reason": "MA5下穿MA20 (死叉)", "price": current_price})
        
    # 2. 风控信号
    cost_price = df['close'].mean() # 简单以20日均价作为参考成本
    if current_price < cost_price * (1 - sl_ratio):
        signals.append({"type": "止损卖出", "reason": f"下跌触发 {sl_ratio*100:.1f}% 止损线", "price": current_price})
    elif current_price > cost_price * (1 + tp_ratio):
        signals.append({"type": "止盈卖出", "reason": f"上涨触发 {tp_ratio*100:.1f}% 止盈线", "price": current_price})
        
    return signals, current_price

# ================= 界面显示区域 =================
st.divider()

if st.session_state.monitoring:
    # 增加“空代码”防御检测
    if not stock_codes:
        st.warning("⚠️ 请先在左侧输入股票代码，然后再开启实时监测！")
    else:
        st.subheader(f"📡 实时行情面板 (更新时间: {datetime.datetime.now().strftime('%H:%M:%S')})")
        
        cols = st.columns(min(len(stock_codes), 3))
        
        for index, code in enumerate(stock_codes):
            df = get_data(code)
            signals, price = analyze_strategy(df, stop_loss, take_profit)
            
            col = cols[index % 3]
            with col:
                if price > 0:
                    st.metric(label=f"**{code}**", value=f"{price:.2f}", delta=None)
                else:
                    st.metric(label=f"**{code}**", value="暂无数据")
                
                if signals:
                    for sig in signals:
                        if sig['type'] == "买入":
                            st.success(f"🔴 **{sig['type']}** 信号: {sig['reason']}")
                        elif sig['type'] == "卖出":
                            st.warning(f"🟢 **{sig['type']}** 信号: {sig['reason']}")
                        else:
                            st.error(f"⛔ **{sig['type']}** 信号: {sig['reason']}")
                else:
                    st.caption("📝 目前无买卖点信号，观望中。")
else:
    st.info("👈 请点击左上角菜单栏的 '开始/暂停 实时滚动监测' 按钮激活分析界面。")
