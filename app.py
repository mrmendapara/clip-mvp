import streamlit as st
import pandas as pd
import numpy as np
import re
import os
from googleapiclient.discovery import build

# -------------------------------
# CONFIG
# -------------------------------
st.set_page_config(page_title="CLIP", layout="wide")

API_KEY = os.getenv("YOUTUBE_API_KEY") or "AIzaSyCz6KIoAGEuWuml4kGQzlB0dX46N5qs1Xw"
youtube = build('youtube', 'v3', developerKey=API_KEY)

# -------------------------------
# MOBILE + CLEAN UI
# -------------------------------
st.markdown("""
<style>
.block-container { padding: 1rem; }

@media (max-width: 768px) {
    div[data-testid="column"] {
        width: 100% !important;
        flex: 100% !important;
    }
}
</style>
""", unsafe_allow_html=True)


st.markdown("""
<style>
.card {
    background: linear-gradient(135deg, #1f2937, #111827);
    padding: 15px;
    border-radius: 12px;
    text-align: center;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}
.card h3 { margin: 0; font-size: 22px; }
.card p { margin: 0; color: #9ca3af; font-size: 12px; }
</style>
""", unsafe_allow_html=True)


st.markdown("""
<style>
html, body, [class*="css"]  {
    background-color: #0E1117;
    color: white;
}

/* Fix tables */
table {
    width: 100%;
    border-collapse: collapse;
}
th, td {
    padding: 8px;
    text-align: left;
}

/* Better spacing */
.block-container {
    padding-top: 1rem;
}
</style>
""", unsafe_allow_html=True)


# -------------------------------
# KPI CALC
# -------------------------------
def compute_kpis(df):

    df = df.copy()
    df["views"] = df["views"].replace(0, np.nan)

    df["engagement_rate"] = ((df["likes"] + df["comments"]) / df["views"]).fillna(0)
    df["views_per_day"] = (df["views"] / df["days_old"]).fillna(0)

    return df

# -------------------------------
# STRATEGY ENGINE
# -------------------------------
def generate_strategy(df):

    top = df.sort_values("engagement_rate", ascending=False).head(3)
    fast = df.sort_values("views_per_day", ascending=False).head(3)

    gems = df[
        (df["engagement_rate"] > df["engagement_rate"].median()) &
        (df["views_per_day"] < df["views_per_day"].median())
    ]

    return top, fast, gems

# -------------------------------
# CHANNEL ID
# -------------------------------
def extract_channel_id(user_input):
    user_input = user_input.strip()

    if user_input.startswith("UC"):
        return user_input

    match = re.search(r"(v=|youtu\.be/)([a-zA-Z0-9_-]+)", user_input)
    if match:
        vid = match.group(2)
        res = youtube.videos().list(part="snippet", id=vid).execute()
        return res["items"][0]["snippet"]["channelId"]

    match = re.search(r"@([a-zA-Z0-9._-]+)", user_input)
    if match:
        res = youtube.search().list(
            part="snippet", q=match.group(1), type="channel", maxResults=1
        ).execute()
        return res["items"][0]["snippet"]["channelId"]

    return None

# -------------------------------
# FETCH DATA
# -------------------------------
def get_videos(channel_id, max_results=20):

    videos = []
    next_page_token = None

    while len(videos) < max_results:

        request = youtube.search().list(
            part="snippet",
            channelId=channel_id,
            maxResults=min(50, max_results - len(videos)),
            order="date",
            pageToken=next_page_token
        )

        response = request.execute()

        for item in response.get("items", []):
            vid = item["id"].get("videoId")
            if not vid:
                continue

            data = youtube.videos().list(
                part="snippet,statistics",
                id=vid
            ).execute().get("items", [])

            if not data:
                continue

            d = data[0]
            s = d["snippet"]
            stats = d.get("statistics", {})

            videos.append({
                "video_id": vid,
                "title": s["title"],
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "published_at": pd.to_datetime(s["publishedAt"], utc=True),
            })

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

    df = pd.DataFrame(videos)

    now = pd.Timestamp.now(tz="UTC")
    df["days_old"] = (now - df["published_at"]).dt.days.clip(lower=1)

    return df

# -------------------------------
# UI
# -------------------------------
st.title("🚀 CLIP - Content Intelligence")

user_input = st.text_input(
    "Paste YouTube Channel / Video URL",
    placeholder="https://youtube.com/@yourchannel"
)

video_limit = st.radio(
    "Select Analysis Size",
    ["Quick (20 videos)", "Deep (200 videos)"],
    horizontal=True
)

MAX_RESULTS = 20 if video_limit == "Quick (20 videos)" else 200


# -------------------------------
# MAIN
# -------------------------------
if st.button("Analyze"):

    if not user_input:
        st.warning("Enter input")
        st.stop()

    st.caption(f"Analyzing {MAX_RESULTS} videos")


    with st.spinner("Analyzing..."):

        channel_id = extract_channel_id(user_input)

        if not channel_id:
            st.error("Invalid input")
            st.stop()

        df = get_videos(channel_id, max_results=MAX_RESULTS)
        df = compute_kpis(df)


        avg_vpd = df["views_per_day"].mean()
        df["performance_ratio"] = df["views_per_day"] / avg_vpd

        def classify(row):
            r = row["performance_ratio"]
            if r < 0.3:
                return "Dead"
            elif r < 0.7:
                return "At Risk"
            else:
                return "Evergreen"

        df["status"] = df.apply(classify, axis=1)



        if df.empty:
            st.warning("No data")
            st.stop()

        # -------------------------------
        # TABS
        # -------------------------------
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 Overview",
            "📈 Performance",
            "🎯 Opportunities",
            "🧠 Strategy",
            "📋 Data Table"
        ])

        # -------------------------------
        # TAB 1
        # -------------------------------
        with tab1:

            st.subheader("📊 Channel Overview")

        
            # -------------------------------
            # OVERVIEW KPI CARDS (8 METRICS)
            # -------------------------------

            df["content_type"] = df["title"].apply(
                lambda x: "Short" if "#shorts" in x.lower() else "Video"
            )

            shorts = df[df["content_type"] == "Short"]
            videos = df[df["content_type"] == "Video"]

            col1, col2, col3, col4 = st.columns(4)
            col5, col6, col7, col8 = st.columns(4)

            # Row 1
            col1.metric("📊 Total Videos", len(df))
            col2.metric("📱 Total Shorts", len(shorts))
            col3.metric("👁️ Video Views", f"{videos['views'].sum():,.0f}")
            col4.metric("👁️ Shorts Views", f"{shorts['views'].sum():,.0f}")

            # Row 2
            col5.metric("📈 Avg Video Views", f"{videos['views'].mean():,.0f}" if not videos.empty else 0)
            col6.metric("⚡ Avg Views/Day", f"{df['views_per_day'].mean():,.0f}")
            col7.metric("💬 Engagement Rate", f"{df['engagement_rate'].mean():.2%}")
            col8.metric("🔥 Evergreen %", f"{(len(df[df['status']=='Evergreen'])/len(df)*100):.0f}%")


            # -------------------------------
            # EXECUTIVE INSIGHTS
            # -------------------------------

            st.divider()
            st.subheader("💡 Key Insights")

            insights = []

            total = len(df)
            dead = len(df[df["status"] == "Dead"])
            evergreen = len(df[df["status"] == "Evergreen"])
            at_risk = len(df[df["status"] == "At Risk"])

            dead_pct = round((dead / total) * 100, 1)

            # 1. Content health
            if dead_pct > 30:
                insights.append(f"🔴 {dead_pct}% of your content is underperforming")
            else:
                insights.append(f"🟢 Only {dead_pct}% content is underperforming")

            # 2. Evergreen strength
            if evergreen > total * 0.4:
                insights.append("🌱 Strong evergreen content base")
            else:
                insights.append("⚠️ Low evergreen content — focus on long-term content")

            # 3. Shorts strategy
            short_ratio = len(shorts) / total if total else 0

            if short_ratio > 0.6:
                insights.append("📱 Shorts-heavy strategy — good for reach")
            elif short_ratio < 0.2:
                insights.append("🎯 Opportunity: Increase Shorts for discoverability")
            else:
                insights.append("⚖️ Balanced Shorts + Long-form strategy")

            # 4. Top performer
            top = df.sort_values("views_per_day", ascending=False).iloc[0]
            insights.append(f"🚀 Top performer: {top['title'][:50]}")

            # 5. Hidden gems
            gems = df[
                (df["engagement_rate"] > df["engagement_rate"].median()) &
                (df["views_per_day"] < df["views_per_day"].median())
            ]

            if not gems.empty:
                insights.append(f"💎 {len(gems)} high-potential videos need promotion")

            # Display
            for i in insights:
                st.info(i)



            # ---------------- MEANINGFUL CHART ----------------
            st.subheader("📊 Content Health Snapshot")

            dead = len(df[df["status"] == "Dead"])
            evergreen = len(df[df["status"] == "Evergreen"])
            at_risk = len(df[df["status"] == "At Risk"])

            total = len(df)
            dead_pct = round((dead / total) * 100, 1)

            # 🔥 HEADLINE INSIGHT
            if dead_pct > 30:
                st.error(f"🔴 {dead_pct}% of your content is underperforming — huge optimization opportunity")
            else:
                st.success(f"🟢 Only {dead_pct}% content underperforming — strong content strategy")

            import plotly.express as px

            fig = px.pie(
                df,
                names="status",
                title="Content Health Distribution",
                color="status",
                color_discrete_map={
                    "Dead": "red",
                    "At Risk": "orange",
                    "Evergreen": "green"
                }
            )

            st.plotly_chart(fig, use_container_width=True)

            st.caption("👉 Evergreen = scalable winners | Dead = optimization opportunity")

        # -------------------------------
        # TAB 2
        # -------------------------------
        with tab2:

            st.subheader("Performance")

            st.info("Top-right = Best content")

            import plotly.express as px

            fig = px.scatter(
                df,
                x="days_old",
                y="views_per_day",
                size="views",
                hover_data=["title"]
            )

            st.plotly_chart(fig, use_container_width=True)

        # -------------------------------
        # TAB 3
        # -------------------------------
        with tab3:

            st.subheader("Opportunities")

            st.info("High engagement + low reach = opportunity")

            import plotly.express as px

            fig = px.scatter(
                df,
                x="views_per_day",
                y="engagement_rate",
                size="views",
                hover_data=["title"]
            )

            st.plotly_chart(fig, use_container_width=True)

        # -------------------------------
        # TAB 4
        # -------------------------------
        with tab4:

            st.subheader("What to Post Next")

            top, fast, gems = generate_strategy(df)

            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("### 🔥 Replicate")
                for t in top["title"]:
                    st.markdown(f"- {t[:60]}")

            with col2:
                st.markdown("### 🚀 Scale")
                for t in fast["title"]:
                    st.markdown(f"- {t[:60]}")

            with col3:
                st.markdown("### 💎 Opportunities")
                for t in gems["title"].head(3):
                    st.markdown(f"- {t[:60]}")


        # -------------------------------
        # TAB 5
        # -------------------------------

        with tab5:

            st.subheader("📋 Video Performance Table")

            df_table = df.copy()

            # -------------------------------
            # FIX 1: Keep video_id for links
            # -------------------------------
            if "video_id" not in df_table.columns:
                df_table["video_id"] = df_table.index.astype(str)

            # -------------------------------
            # FIX 2: SORT properly (no df overwrite)
            # -------------------------------
            status_order = {"Evergreen": 0, "At Risk": 1, "Dead": 2}
            df_table["status_order"] = df_table["status"].map(status_order)

            df_table = df_table.sort_values(
                by=["status_order", "views_per_day"],
                ascending=[True, False]
            )

            # -------------------------------
            # FORMAT
            # -------------------------------
            df_table["Title"] = df_table["title"].apply(
                lambda x: x[:60] + "..." if len(x) > 60 else x
            )

            df_table["Link"] = df_table["video_id"].apply(
                lambda vid: f'<a href="https://www.youtube.com/watch?v={vid}" target="_blank">Watch</a>'
            )

            df_table["Engagement"] = (df_table["engagement_rate"] * 100).round(2).astype(str) + "%"
            df_table["Views/Day"] = df_table["views_per_day"].round(0)
            df_table["Perf Score"] = df_table["performance_ratio"].round(2)

            # -------------------------------
            # STATUS COLOR
            # -------------------------------
            def color_status(x):
                return "green" if x == "Evergreen" else "orange" if x == "At Risk" else "red"

            df_table["Status"] = df_table["status"].apply(
                lambda x: f'<span style="color:{color_status(x)}; font-weight:bold">{x}</span>'
            )

            df_table = df_table[[
                "Title",
                "views",
                "Views/Day",
                "Engagement",
                "Perf Score",
                "Status",
                "Link"
            ]].rename(columns={"views": "Views"})

            st.markdown(
                df_table.to_html(escape=False, index=False),
                unsafe_allow_html=True
            )