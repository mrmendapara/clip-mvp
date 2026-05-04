import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
import re
import os



import numpy as np
import pandas as pd

# -------------------------------
# KPI CALCULATIONS
# -------------------------------

def compute_kpis(df):

    df = df.copy()

    # Avoid divide-by-zero issues
    df["views"] = df["views"].replace(0, np.nan)

    # ---------------- Engagement KPIs ----------------
    df["engagement_rate"] = ((df["likes"] + df["comments"]) / df["views"]).fillna(0)
    df["like_rate"] = (df["likes"] / df["views"]).fillna(0)
    df["comment_rate"] = (df["comments"] / df["views"]).fillna(0)

    # ---------------- Growth KPIs ----------------
    df["views_per_day"] = (df["views"] / df["days_old"]).replace([np.inf, -np.inf], 0).fillna(0)

    df["velocity_score"] = df["views_per_day"] * df["engagement_rate"]

    # ---------------- Content Health ----------------
    df["content_strength"] = (
        df["engagement_rate"] * 0.5 +
        df["like_rate"] * 0.3 +
        df["comment_rate"] * 0.2
    )

    # ---------------- Opportunity Score ----------------
    df["opportunity_score"] = (
        (df["engagement_rate"] * 100) -
        (df["views_per_day"] / df["views_per_day"].max() * 50)
    )

    # ---------------- Final Score ----------------
    df["final_score"] = (
        df["content_strength"] * 40 +
        df["velocity_score"] * 30 +
        df["opportunity_score"] * 30
    )

    return df




def generate_next_content_strategy(df):

    insights = []

    # 1. Best performing videos
    top = df.sort_values("engagement_rate", ascending=False).head(3)

    top_topics = top["title"].tolist()

    insights.append("🔥 Based on your top-performing content:")

    for t in top_topics:
        insights.append(f"👉 Replicate theme from: {t[:70]}")

    # 2. High velocity content
    fast_growth = df.sort_values("views_per_day", ascending=False).head(3)

    insights.append("\n🚀 High momentum formats:")

    for t in fast_growth["title"].tolist():
        insights.append(f"👉 Scale similar content to: {t[:70]}")

    # 3. Underutilized gems
    gems = df[(df["engagement_rate"] > df["engagement_rate"].median()) &
              (df["views_per_day"] < df["views_per_day"].median())]

    if not gems.empty:
        insights.append("\n💎 Hidden opportunities:")

        for t in gems["title"].head(3).tolist():
            insights.append(f"👉 Boost distribution of: {t[:70]}")

    return insights


st.markdown("""
<style>
/* Global spacing */
.block-container {
    padding-top: 1.5rem;
    padding-bottom: 1rem;
}

/* Card style */
.card {
    background-color: #161B22;
    padding: 20px;
    border-radius: 12px;
    box-shadow: 0 0 10px rgba(0,0,0,0.3);
    margin-bottom: 15px;
}

/* KPI number */
.kpi {
    font-size: 28px;
    font-weight: bold;
}

/* KPI label */
.kpi-label {
    font-size: 14px;
    color: #9BA3AF;
}

/* Section titles */
.section-title {
    font-size: 20px;
    font-weight: 600;
    margin-bottom: 10px;
}
</style>
""", unsafe_allow_html=True)



# -------------------------------
# CONFIG
# -------------------------------
API_KEY = os.getenv("YOUTUBE_API_KEY") or "AIzaSyCz6KIoAGEuWuml4kGQzlB0dX46N5qs1Xw"
youtube = build('youtube', 'v3', developerKey=API_KEY)

st.set_page_config(page_title="CLIP", layout="wide")

# -------------------------------
# EXTRACT CHANNEL ID
# -------------------------------
def extract_channel_id(user_input, youtube):
    user_input = user_input.strip()

    if user_input.startswith("UC"):
        return user_input

    video_match = re.search(r"(v=|youtu\.be/)([a-zA-Z0-9_-]+)", user_input)
    if video_match:
        video_id = video_match.group(2)
        response = youtube.videos().list(part="snippet", id=video_id).execute()
        if response.get("items"):
            return response["items"][0]["snippet"]["channelId"]

    channel_match = re.search(r"youtube\.com/channel/(UC[a-zA-Z0-9_-]+)", user_input)
    if channel_match:
        return channel_match.group(1)

    handle_match = re.search(r"@([a-zA-Z0-9._-]+)", user_input)
    if handle_match:
        handle = handle_match.group(1)
        response = youtube.search().list(
            part="snippet",
            q=handle,
            type="channel",
            maxResults=1
        ).execute()
        if response.get("items"):
            return response["items"][0]["snippet"]["channelId"]

    return None

from datetime import datetime
import pandas as pd

# -------------------------------
# GET VIDEOS (CLEAN + SAFE + KPI READY)
# -------------------------------
def get_channel_videos(channel_id):
    videos = []

    search_response = youtube.search().list(
        part="snippet",
        channelId=channel_id,
        maxResults=20,
        order="date"
    ).execute()

    for item in search_response.get("items", []):

        video_id = item["id"].get("videoId")
        if not video_id:
            continue

        video_response = youtube.videos().list(
            part="snippet,statistics",
            id=video_id
        ).execute()

        if not video_response.get("items"):
            continue

        video_data = video_response["items"][0]

        snippet = video_data.get("snippet", {})
        stats = video_data.get("statistics", {})

        title = snippet.get("title", "N/A")

        # STEP 1: Shorts detection
        is_short = "#shorts" in title.lower()

        # ---------------- SAFE EXTRACTION ----------------
        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))

        published_at = snippet.get("publishedAt")

        # ---------------- TIMEZONE SAFE CONVERSION ----------------
        published_at_dt = pd.to_datetime(
            published_at,
            utc=True,
            errors="coerce"
        )

        videos.append({
            "video_id": video_id,
            "title": title,
            "published_at": published_at_dt,
            "views": views,
            "likes": likes,
            "comments": comments,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "content_type": "Short" if is_short else "Video"
        })

    df = pd.DataFrame(videos)

    # ---------------- DERIVED FIELD (FIXED TIMEZONE ISSUE) ----------------
    if not df.empty:

        # FIX: use UTC-aware timestamp
        now = pd.Timestamp.now(tz="UTC")

        df["days_old"] = (now - df["published_at"]).dt.days

        # Clean edge cases
        df["days_old"] = df["days_old"].fillna(1)
        df["days_old"] = df["days_old"].apply(lambda x: max(int(x), 1))

    else:
        df["days_old"] = []

    return df




# -------------------------------
# UI
# -------------------------------
st.title("🚀 CLIP - Content Lifecycle Intelligence")
st.caption("Identify dead vs evergreen content on YouTube")

user_input = st.text_input(
    "Paste YouTube Video / Channel / @handle",
    value="https://www.youtube.com/@googledevelopers"
)

def generate_insights(df):
    insights = []

    total = len(df)
    dead = len(df[df["status"] == "Dead"])
    evergreen = len(df[df["status"] == "Evergreen"])
    at_risk = len(df[df["status"] == "At Risk"])

    dead_pct = round((dead / total) * 100, 1) if total else 0

    # Insight 1: content health
    if dead_pct > 30:
        insights.append(f"🔴 High underperforming content: {dead_pct}% videos are dead or inactive")
    else:
        insights.append(f"🟢 Healthy content mix: only {dead_pct}% underperforming videos")

    # Insight 2: evergreen strength
    if evergreen > total * 0.4:
        insights.append("🌱 Strong evergreen base detected (good long-term content strategy)")
    else:
        insights.append("⚠️ Low evergreen ratio — consider creating more long-term content")

    # Insight 3: at risk content
    if at_risk > 0:
        insights.append(f"⚠️ {at_risk} videos are at risk and need optimization")

    # Insight 4: performance signal
    top = df.sort_values("views_per_day", ascending=False).iloc[0]
    insights.append(f"🚀 Top performer: '{top['title'][:50]}...' driving highest engagement")


    # -------------------------------
    # Shorts vs Video Strategy Insight (STEP 5)
    # -------------------------------
    shorts_df = df[df["content_type"] == "Short"]
    videos_df = df[df["content_type"] == "Video"]

    if len(df) > 0:
        short_ratio = len(shorts_df) / len(df)

        if short_ratio > 0.6:
            insights.append("📱 Shorts-heavy strategy detected — optimize for high-frequency posting")
        elif short_ratio < 0.2:
            insights.append("🎯 Opportunity: Increase Shorts content to boost reach and discoverability")
        else:
            insights.append("⚖️ Balanced content mix — maintain Shorts + long-form synergy")



    return insights


# -------------------------------
# MAIN ACTION
# -------------------------------
if st.button("Analyze Channel"):

    if not user_input:
        st.warning("Please enter valid input")
    else:
        with st.spinner("Analyzing..."):

            channel_id = extract_channel_id(user_input, youtube)

            if not channel_id:
                st.error("Could not extract channel ID")
            else:
                st.success(f"Channel detected: {channel_id}")

                df = get_channel_videos(channel_id)
                df = compute_kpis(df)


                df["content_type"] = df["content_type"].fillna("Video")


                if df.empty:
                    st.warning("No videos found")
                else:
                    # -------------------------------
                    # ADVANCED SCORING
                    # -------------------------------
                    df["published_at"] = pd.to_datetime(
                        df["published_at"], errors="coerce"
                    ).dt.tz_localize(None)

                    df = df.dropna(subset=["published_at"])

                    df["days_old"] = (pd.Timestamp.now() - df["published_at"]).dt.days
                    df["days_old"] = df["days_old"].apply(lambda x: x if x > 0 else 1)

                    df["views_per_day"] = df["views"] / df["days_old"]

                    avg_vpd = df["views_per_day"].mean()
                    df["performance_ratio"] = df["views_per_day"] / avg_vpd

                    def score_video(row):
                        r = row["performance_ratio"]
                        if r < 0.3:
                            return 20
                        elif r < 0.7:
                            return 50
                        elif r < 1.5:
                            return 70
                        else:
                            return 90

                    def classify(score):
                        if score < 40:
                            return "Dead"
                        elif score < 70:
                            return "At Risk"
                        else:
                            return "Evergreen"

                    df["score"] = df.apply(score_video, axis=1)
                    df["status"] = df["score"].apply(classify)

                    def generate_top_insights(df):
                        insights = []

                        total = len(df)
                        dead = len(df[df["status"] == "Dead"])
                        evergreen = len(df[df["status"] == "Evergreen"])

                        # % dead content
                        dead_pct = round((dead / total) * 100, 1)
                        if dead_pct > 30:
                            insights.append(f"🔴 {dead_pct}% of content is underperforming — cleanup opportunity")

                        # Best performer
                        top_video = df.sort_values("views_per_day", ascending=False).iloc[0]
                        insights.append(f"🚀 Top video: '{top_video['title'][:50]}' driving high engagement")

                        # Worst performer
                        worst_video = df.sort_values("views_per_day").iloc[0]
                        insights.append(f"⚠️ Low performer: '{worst_video['title'][:50]}' needs optimization")

                        # Evergreen signal
                        if evergreen > total * 0.4:
                            insights.append("🌱 Strong evergreen content base — good for long-term growth")

                        return insights     

                    # -------------------------------
                    # AI RECOMMENDATION ENGINE (RULE-BASED)
                    # -------------------------------
                    def generate_recommendation(row):
                        ratio = row["performance_ratio"]
                        days = row["days_old"]
                        views = row["views"]

                        if ratio < 0.3:
                            if days > 180:
                                return "❌ Low performance & old → Consider archiving or updating content"
                            else:
                                return "⚠️ Low traction → Improve title, thumbnail, or distribution"

                        elif ratio < 0.7:
                            return "⚠️ Below average → Optimize SEO, title, and thumbnail"

                        else:
                            if days > 365:
                                return "🌱 Evergreen → Consider reposting or repurposing"
                            else:
                                return "✅ Performing well → No action needed"

                    df["recommendation"] = df.apply(generate_recommendation, axis=1)

                    # -------------------------------
                    # KPI
                    # -------------------------------
                    total = len(df)
                    dead = len(df[df["status"] == "Dead"])
                    at_risk = len(df[df["status"] == "At Risk"])
                    evergreen = len(df[df["status"] == "Evergreen"])

                    col1, col2, col3, col4 = st.columns(4)

                    def kpi_card(title, value, color):
                        return f"""
                        <div class="card">
                            <div class="kpi" style="color:{color}">{value}</div>
                            <div class="kpi-label">{title}</div>
                        </div>
                        """

                    col1.markdown(kpi_card("Total Videos", total, "#00C2FF"), unsafe_allow_html=True)
                    col2.markdown(kpi_card("Dead", dead, "#FF4B4B"), unsafe_allow_html=True)
                    col3.markdown(kpi_card("At Risk", at_risk, "#FFA500"), unsafe_allow_html=True)
                    col4.markdown(kpi_card("Evergreen", evergreen, "#00FFAA"), unsafe_allow_html=True)

                    st.divider()


                    st.subheader("💡 Key Insights")

                    insights = generate_insights(df)

                    for i in insights:
                        st.info(i)

                    st.divider()


                    st.subheader("📊 Content Intelligence KPIs")

                    col1, col2, col3, col4 = st.columns(4)

                    col1.metric(
                        "Engagement Rate",
                        f"{df['engagement_rate'].mean():.2%}"
                    )

                    col2.metric(
                        "Like Rate",
                        f"{df['like_rate'].mean():.2%}"
                    )

                    col3.metric(
                        "Comment Rate",
                        f"{df['comment_rate'].mean():.2%}"
                    )

                    col4.metric(
                        "Avg Velocity",
                        f"{df['velocity_score'].mean():.0f}"
                    )


                    import plotly.express as px

                    st.subheader("🔥 Content Opportunity Heatmap")

                    fig_heatmap = px.scatter(
                        df,
                        x="views_per_day",
                        y="engagement_rate",
                        size="views",
                        color="status",
                        hover_data=["title", "views", "likes", "comments"],
                        title="Opportunity Heatmap: Momentum vs Engagement"
                    )

                    st.plotly_chart(fig_heatmap, use_container_width=True, key="heatmap")




                    st.subheader("🧠 Growth Strategy Engine")

                    strategy = generate_next_content_strategy(df)
                    strategy = [s.replace("\n", " ").strip() for s in strategy]

                    replicate = [s for s in strategy if "Replicate" in s or "top-performing" in s]
                    scale = [s for s in strategy if "momentum" in s or "Scale" in s]
                    gems = [s for s in strategy if "Hidden" in s or "opportunity" in s]

                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.markdown("### 🔥 Replicate Winners")
                        for item in replicate[:3]:
                            st.info(item)

                    with col2:
                        st.markdown("### 🚀 Scale Fast Content")
                        for item in scale[:3]:
                            st.success(item)

                    with col3:
                        st.markdown("### 💎 Hidden Opportunities")
                        for item in gems[:3]:
                            st.warning(item)


                    st.subheader("📱 Content Format Analysis")

                    col1, col2 = st.columns(2)

                    shorts_df = df[df["content_type"] == "Short"]
                    videos_df = df[df["content_type"] == "Video"]

                    with col1:
                        st.metric("Shorts Count", len(shorts_df))
                        st.metric("Avg Shorts Views", f"{shorts_df['views'].mean():.0f}" if not shorts_df.empty else 0)

                    with col2:
                        st.metric("Videos Count", len(videos_df))
                        st.metric("Avg Video Views", f"{videos_df['views'].mean():.0f}" if not videos_df.empty else 0)




                    # -------------------------------
                    # CHART
                    # -------------------------------
                    st.subheader("📊 Content Health")
                    st.bar_chart(df["status"].value_counts())

                    
                    import plotly.express as px

                    
                    fig1 = px.pie(df, names="status", title="Content Distribution")
                    fig2 = px.scatter(
                        df,
                        x="days_old",
                        y="views_per_day",
                        color="status",
                        size="views",
                        hover_data=["title"],
                        title="Performance vs Age"
                    )

                    colA, colB = st.columns(2)

                    with colA:
                        st.plotly_chart(fig1, use_container_width=True, key="pie_chart")

                    with colB:
                        st.plotly_chart(fig2, use_container_width=True, key="scatter_chart")

                    st.divider()

                    import plotly.express as px

                    fig = px.box(
                        df,
                        x="content_type",
                        y="views",
                        color="content_type",
                        title="Shorts vs Long-form Performance Distribution"
                    )

                    st.plotly_chart(fig, use_container_width=True, key="format_compare")


                    st.subheader("📊 Content Intelligence Dashboard")

                    import plotly.express as px

                    # -------------------------------
                    # CHART 1: Engagement Map
                    # -------------------------------
                    fig3 = px.scatter(
                        df,
                        x="views",
                        y="engagement_rate",
                        color="content_strength",
                        size="views",
                        hover_data=["title"],
                        title="Engagement vs Views (Content Quality Map)"
                    )

                    st.plotly_chart(fig3, use_container_width=True, key="engagement_chart")

                    # -------------------------------
                    # CHART 2: Opportunity Matrix
                    # -------------------------------
                    fig4 = px.scatter(
                        df,
                        x="views_per_day",
                        y="opportunity_score",
                        color="final_score",
                        size="views",
                        hover_data=["title"],
                        title="Opportunity Detection Matrix"
                    )

                    st.plotly_chart(fig4, use_container_width=True, key="opportunity_chart")





                    # -------------------------------
                    # TABLE PREP
                    # -------------------------------
                    df["url"] = "https://www.youtube.com/watch?v=" + df["video_id"]

                    df["short_title"] = df["title"].apply(
                        lambda x: x[:60] + "..." if len(x) > 60 else x
                    )

                    df["views"] = df["views"].astype(int)
                    df["views_per_day"] = df["views_per_day"].round(0).astype(int)
                    df["performance_ratio"] = df["performance_ratio"].round(2)
                    df["score"] = df["score"].round(0).astype(int)




                    df_table = df[[
                        "short_title",
                        "views",
                        "views_per_day",
                        "performance_ratio",
                        "score",
                        "status",
                        "recommendation",
                        "url"
                    ]].sort_values(by="views_per_day", ascending=False)

                    df_table = df_table.rename(columns={
                        "short_title": "Title",
                        "views": "Views",
                        "views_per_day": "Views/Day",
                        "performance_ratio": "Perf Ratio",
                        "score": "Score",
                        "status": "Status",
                        "recommendation": "AI Insight",
                        "url": "Link"
                    })

                    # Make Title clickable
                    df_table["Title"] = df_table.apply(
                        lambda row: f'<a href="{row["Link"]}" target="_blank">{row["Title"]}</a>',
                        axis=1
                    )

                    # Format AI Insight column
                    df_table["AI Insight"] = df_table["AI Insight"].apply(
                        lambda x: f"<span>{x}</span>"
                    )

                    # Color status
                    def color_status(status):
                        if status == "Dead":
                            return "red"
                        elif status == "At Risk":
                            return "orange"
                        else:
                            return "green"

                    df_table["Status"] = df_table["Status"].apply(
                        lambda x: f'<span style="color:{color_status(x)}; font-weight:bold">{x}</span>'
                    )

                    df_table = df_table.drop(columns=["Link"])

                    # -------------------------------
                    # DISPLAY TABLE
                    # -------------------------------
                    st.subheader("📋 Video Performance")

                    st.markdown("""
                    <style>
                    table { width: 100%; }
                    th { text-align: left; padding: 8px; }
                    td { padding: 6px; }
                    </style>
                    """, unsafe_allow_html=True)

                    st.markdown(
                        df_table.to_html(escape=False, index=False),
                        unsafe_allow_html=True
                    )

                    # -------------------------------
                    # HELP SECTION
                    # -------------------------------
                    with st.expander("📘 Understand Metrics"):
                        st.markdown("""
**Performance Ratio**
= Views per day ÷ Channel average

**Categories**
- 🪦 Dead (<0.3): Low visibility  
- ⚠️ At Risk (0.3–0.7): Needs improvement  
- 🌱 Evergreen (>0.7): Strong performers  

**Why it matters**
Focus on content to optimize, remove, or replicate.
""")