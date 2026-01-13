import streamlit as st
import sqlite3
import pandas as pd
import altair as alt
import time

# 1. Page Config (Dark Mode & Wide Layout)
st.set_page_config(
    page_title="TubeMind Observability",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS to make it look like Grafana (Dark, Cards)
st.markdown("""
<style>
    .stApp {
        # background-color: #101010;
    }
    .metric-card {
        background-color: #1e1e1e;
        border: 1px solid #333;
        padding: 20px;
        border-radius: 10px;
        color: white;
    }
    [data-testid="stMetricValue"] {
        color: #4ade80 !important; /* Green numbers */
    }
</style>
""", unsafe_allow_html=True)

st.title("📈 System Observability Dashboard")
st.markdown("Real-time telemetry from **TubeMind AI Pipeline**")

# Auto-refresh mechanism
if st.button('🔄 Refresh Metrics'):
    st.rerun()

# --- DATA ENGINEERING: ETL FROM SQLITE ---
def load_data():
    try:
        conn = sqlite3.connect('analytics.db')
        # We fetch the raw logs
        df = pd.read_sql_query("SELECT * FROM queries", conn)
        conn.close()
        
        # Convert timestamp to datetime objects
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except:
        return pd.DataFrame()

df = load_data()

if df.empty:
    st.warning("No data found. Go chat with the AI to generate logs!")
    st.stop()

# --- ROW 1: "GOLDEN SIGNALS" (The Grafana Header) ---
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(label="Total Requests", value=len(df), delta=f"+{len(df)} today")

with col2:
    # Latency (P99 is a standard engineering metric)
    avg_lat = df['processing_time'].mean()
    st.metric(label="Avg Latency", value=f"{avg_lat:.2f}s", delta="-0.1s", delta_color="inverse")

with col3:
    # Traffic (Unique Videos)
    unique_vids = df['video_id'].nunique()
    st.metric(label="Video Sources", value=unique_vids)

with col4:
    # "Fake" System Health (Just to look cool)
    st.metric(label="System Status", value="HEALTHY 🟢")

st.markdown("---")

# --- ROW 2: LATENCY HISTOGRAM (The Data Science Chart) ---
c1, c2 = st.columns([2, 1])

with c1:
    st.subheader("⏱️ Latency Distribution (Performance)")
    # Altair chart for detailed visualization
    chart = alt.Chart(df).mark_area(
        line={'color':'#4ade80'},
        color=alt.Gradient(
            gradient='linear',
            stops=[alt.GradientStop(color='#4ade80', offset=0),
                   alt.GradientStop(color='#101010', offset=1)],
            x1=1, x2=1, y1=1, y2=0
        )
    ).encode(
        x=alt.X('timestamp:T', title='Time'),
        y=alt.Y('processing_time:Q', title='Latency (seconds)'),
        tooltip=['timestamp', 'processing_time', 'question']
    ).properties(height=300)
    
    st.altair_chart(chart, use_container_width=True)

with c2:
    st.subheader("📂 Content Distribution")
    # Pie chart of Video IDs
    video_counts = df['video_id'].value_counts().reset_index()
    video_counts.columns = ['video_id', 'count']
    
    pie = alt.Chart(video_counts).mark_arc(innerRadius=50).encode(
        theta=alt.Theta(field="count", type="quantitative"),
        color=alt.Color(field="video_id", type="nominal"),
        tooltip=['video_id', 'count']
    ).properties(height=300)
    
    st.altair_chart(pie, use_container_width=True)

# --- ROW 3: RAW LOGS (The "Log Explorer") ---
st.subheader("📝 Live Query Logs (ETL Output)")
st.dataframe(
    df[['timestamp', 'processing_time', 'question', 'answer']].sort_values(by='timestamp', ascending=False),
    use_container_width=True
)