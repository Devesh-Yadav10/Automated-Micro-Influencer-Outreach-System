"""Streamlit demonstration dashboard for the Automated Micro-Influencer Outreach System."""

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from config.settings import get_settings
from src.discovery.seed_source import SeedFileDiscoverySource
from src.filtering.pipeline import FilteringPipeline
from src.outreach.dispatcher import OutreachDispatcher
from src.personalization.llm_client import PersonalizationEngine
from src.personalization.validator import validate_email_pitch, validate_instagram_dm
from src.storage.database import DatabaseManager

# Page setup
st.set_page_config(
    page_title="Micro-Influencer Outreach System",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #1E3A8A; margin-bottom: 0.5rem; }
    .sub-header { font-size: 1.1rem; color: #4B5563; margin-bottom: 1.5rem; }
    .stat-card { background-color: #F3F4F6; padding: 1.2rem; border-radius: 0.6rem; border-left: 5px solid #3B82F6; }
    .badge-qual { background-color: #DEF7EC; color: #03543F; padding: 4px 10px; border-radius: 12px; font-weight: 600; }
    .badge-disq { background-color: #FDE8E8; color: #9B1C1C; padding: 4px 10px; border-radius: 12px; font-weight: 600; }
    .badge-rev { background-color: #FEF08A; color: #713F12; padding: 4px 10px; border-radius: 12px; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_db():
    settings = get_settings()
    return DatabaseManager(settings.get_db_path())


db = get_db()
settings = get_settings()

# Sidebar Navigation
st.sidebar.title("🎯 Navigation")
view_mode = st.sidebar.radio(
    "Go to",
    [
        "📊 System Overview",
        "🔍 Influencer Explorer",
        "⚖️ Filtering & Audit",
        "✍️ Personalized Pitches",
        "🚀 Outreach Tracker",
        "📁 Import & Export",
    ],
)

st.sidebar.markdown("---")
st.sidebar.markdown(f"**App Env**: `{settings.APP_ENV}`")
st.sidebar.markdown(f"**Outreach Mode**: `{settings.OUTREACH_MODE}`")
st.sidebar.markdown(f"**LLM Provider**: `{settings.LLM_PROVIDER}`")
st.sidebar.markdown(
    f"**YouTube API**: `{'Configured' if settings.YOUTUBE_API_KEY else 'Seed Mode'}`"
)

# Load data from database
influencers = db.list_influencers()
audits_by_id = db.get_latest_filtering_audits()
counts = db.get_counts()


# Section 1: System Overview
if view_mode == "📊 System Overview":
    st.markdown('<div class="main-header">System Health & Performance Overview</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Real-time status of discovered micro-influencers, qualification audits, and simulated outreach.</div>', unsafe_allow_html=True)

    if not influencers:
        st.warning("No influencer records found in the database. Please import the seed dataset using the button below or in the Import/Export tab.")
        if st.button("📥 Import 52 Verified Tech Creators Now"):
            source = SeedFileDiscoverySource()
            profs = source.discover(file_path=Path("data/verified_tech_influencers.json"), allow_fictional=False)
            for p in profs:
                db.insert_influencer(p)
            st.success(f"Successfully loaded {len(profs)} profiles!")
            st.rerun()
    else:
        # Key Metrics Row
        total_inf = len(influencers)
        qual_count = sum(1 for a in audits_by_id.values() if a.classification == "QUALIFIED")
        disq_count = sum(1 for a in audits_by_id.values() if a.classification == "DISQUALIFIED")
        rev_count = sum(1 for a in audits_by_id.values() if a.classification == "NEEDS_REVIEW")
        has_email_count = sum(1 for p in influencers if p.contact_email != "Not Found")
        outreach_count = counts["outreach_logs"]

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total Profiles", total_inf)
        col2.metric("Qualified Micro-Tier", qual_count, f"{round(qual_count/total_inf*100, 1)}%" if total_inf else "0%")
        col3.metric("Disqualified", disq_count)
        col4.metric("Verified Public Emails", has_email_count, f"{round(has_email_count/total_inf*100, 1)}%" if total_inf else "0%")
        col5.metric("Outreach Dispatches", outreach_count, f"{settings.OUTREACH_MODE.title()} Mode")

        st.markdown("---")

        c_left, c_right = st.columns(2)

        with c_left:
            st.subheader("Audience Size Distribution")
            df_inf = pd.DataFrame([
                {
                    "Name": p.name,
                    "Subscribers": p.follower_count,
                    "Classification": audits_by_id[p.id].classification if p.id in audits_by_id else "UNAUDITED",
                    "Engagement Rate (%)": p.engagement_rate or 0.0,
                }
                for p in influencers
            ])
            st.bar_chart(df_inf, x="Name", y="Subscribers")

        with c_right:
            st.subheader("Classification Breakdown")
            breakdown_data = pd.DataFrame([
                {"Status": "QUALIFIED", "Count": qual_count},
                {"Status": "DISQUALIFIED", "Count": disq_count},
                {"Status": "NEEDS_REVIEW", "Count": rev_count},
                {"Status": "UNAUDITED", "Count": max(0, total_inf - len(audits_by_id))},
            ])
            st.dataframe(breakdown_data, use_container_width=True)

            st.info(
                "💡 **Deduplication & Safety Policy**: The outreach sending layer strictly operates in "
                "**simulation mode** by default. Duplicate outreach to the same creator on the same channel is rejected."
            )


# Section 2: Influencer Explorer
elif view_mode == "🔍 Influencer Explorer":
    st.markdown('<div class="main-header">Micro-Influencer Explorer</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Inspect genuine discovered profiles, public metrics, verified content themes, and data provenance.</div>', unsafe_allow_html=True)

    if not influencers:
        st.info("No profiles available to display.")
    else:
        # Search & Filter bar
        col_s, col_n, col_c, col_e = st.columns([2, 1.5, 1.5, 1.5])
        with col_s:
            search_query = st.text_input("Search by Name or Handle", "").strip().lower()
        with col_n:
            all_niches = sorted(list(set(p.niche for p in influencers)))
            sel_niche = st.selectbox("Filter by Niche", ["All"] + all_niches)
        with col_c:
            sel_class = st.selectbox("Classification", ["All", "QUALIFIED", "DISQUALIFIED", "NEEDS_REVIEW"])
        with col_e:
            sel_email = st.selectbox("Email Availability", ["All", "Verified Only", "Not Found Only"])

        # Filter logic
        filtered = []
        for p in influencers:
            p_class = audits_by_id[p.id].classification if p.id in audits_by_id else "UNAUDITED"

            if search_query and (search_query not in p.name.lower() and (not p.handle or search_query not in p.handle.lower())):
                continue
            if sel_niche != "All" and p.niche != sel_niche:
                continue
            if sel_class != "All" and p_class != sel_class:
                continue
            if sel_email == "Verified Only" and p.contact_email == "Not Found":
                continue
            if sel_email == "Not Found Only" and p.contact_email != "Not Found":
                continue
            filtered.append(p)

        st.markdown(f"**Showing {len(filtered)} of {len(influencers)} creator profiles**")

        # Table Display
        table_rows = []
        for p in filtered:
            p_audit = audits_by_id.get(p.id)
            status_label = p_audit.classification if p_audit else "UNAUDITED"
            table_rows.append({
                "ID": p.id[:8] + "...",
                "Name": p.name,
                "Handle": p.handle or "N/A",
                "Subscribers": f"{p.follower_count:,}",
                "Engagement Proxy": f"{p.engagement_rate}%" if p.engagement_rate is not None else "Unknown",
                "Contact Email": p.contact_email,
                "Status": status_label,
                "Themes": ", ".join(p.content_themes[:3]),
                "Profile URL": p.profile_url,
            })

        df_display = pd.DataFrame(table_rows)
        st.dataframe(df_display, use_container_width=True)

        # Profile Inspector Expander
        st.subheader("Creator Profile Deep Dive")
        selected_name = st.selectbox("Select Creator to Inspect", [p.name for p in filtered])
        selected_p = next((p for p in filtered if p.name == selected_name), None)

        if selected_p:
            d_col1, d_col2 = st.columns([1, 1])
            with d_col1:
                st.markdown(f"### {selected_p.name} ({selected_p.handle})")
                st.markdown(f"**Platform**: `{selected_p.platform.capitalize()}` | **Niche**: `{selected_p.niche}`")
                st.markdown(f"**Followers/Subscribers**: `{selected_p.follower_count:,}`")
                st.markdown(f"**Engagement Rate Proxy**: `{selected_p.engagement_rate}%`" if selected_p.engagement_rate else "**Engagement Rate**: `Unknown`")
                st.markdown(f"**Contact Email**: `{selected_p.contact_email}`")
                st.markdown(f"**Channel URL**: [{selected_p.profile_url}]({selected_p.profile_url})")
            with d_col2:
                st.markdown("**Public Channel Bio / Description**")
                st.info(selected_p.bio or "No bio available in metadata.")
                st.markdown(f"**Content Themes**: {', '.join(selected_p.content_themes)}")
                st.markdown(f"**Data Provenance**: `{selected_p.source_url}`")
                st.markdown(f"**Collected At**: `{selected_p.collected_at.strftime('%Y-%m-%d %H:%M:%S UTC')}`")


# Section 3: Filtering & Audit Trail
elif view_mode == "⚖️ Filtering & Audit":
    st.markdown('<div class="main-header">Filtering & Audit Trail</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Evaluate creators against transparent micro-influencer rules and inspect pass/fail audit logs.</div>', unsafe_allow_html=True)

    with st.expander("⚙️ Adjust Filtering Parameters", expanded=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        with f_col1:
            p_min_f = st.number_input("Min Followers", min_value=1000, max_value=50000, value=5000, step=1000)
        with f_col2:
            p_max_f = st.number_input("Max Followers", min_value=20000, max_value=500000, value=100000, step=10000)
        with f_col3:
            p_niche = st.text_input("Target Niche", "Technology / AI / Machine Learning")
        with f_col4:
            p_eng = st.number_input("Min Engagement Rate (%) [0 = unconstrained]", min_value=0.0, max_value=10.0, value=0.0, step=0.5)
            min_eng = p_eng if p_eng > 0 else None

        if st.button("🚀 Run Filtering Pipeline on Stored Creators"):
            pipeline = FilteringPipeline(
                db=db,
                min_followers=p_min_f,
                max_followers=p_max_f,
                target_niche=p_niche,
                min_engagement_rate=min_eng,
            )
            audits = pipeline.evaluate_all(profiles=influencers, persist=True)
            st.success(f"Successfully evaluated {len(audits)} creators against ruleset {pipeline.ruleset_version}!")
            st.rerun()

    st.markdown("---")
    st.subheader("Auditing History & Justification Logs")

    all_audits = []
    for p in influencers:
        p_audits = db.get_filtering_audits_for_influencer(p.id)
        if p_audits:
            latest = p_audits[0]
            all_audits.append({
                "Influencer": p.name,
                "Audience Size": f"{p.follower_count:,}",
                "Classification": latest.classification,
                "Passed": "YES" if latest.passed else "NO",
                "Primary Justification": latest.reasons[0] if latest.reasons else "No reason recorded",
                "Evaluated At": latest.evaluated_at.strftime("%Y-%m-%d %H:%M:%S"),
            })

    if all_audits:
        df_audit = pd.DataFrame(all_audits)
        st.dataframe(df_audit, use_container_width=True)

        csv_data = df_audit.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Audit Trail CSV",
            data=csv_data,
            file_name=f"micro_influencer_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )
    else:
        st.info("No audit evaluations recorded yet. Run the pipeline above.")


# Section 4: Personalized Pitch Studio
elif view_mode == "✍️ Personalized Pitches":
    st.markdown('<div class="main-header">Personalized Pitch Studio</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Generate authentic, strictly length-validated email collaboration pitches and Instagram DMs.</div>', unsafe_allow_html=True)

    qualified_profs = [
        p for p in influencers
        if p.id in audits_by_id and audits_by_id[p.id].classification == "QUALIFIED"
    ]

    if not qualified_profs:
        st.warning("No qualified creators found. Run the filtering pipeline to qualify micro-influencer candidates.")
    else:
        creator_names = [p.name for p in qualified_profs]
        selected_creator_name = st.selectbox("Select Qualified Creator to Pitch", creator_names)
        creator_p = next(p for p in qualified_profs if p.name == selected_creator_name)

        col_meta1, col_meta2 = st.columns(2)
        with col_meta1:
            st.markdown(f"**Target Handle**: `{creator_p.handle or 'N/A'}` | **Followers**: `{creator_p.follower_count:,}`")
            st.markdown(f"**Verified Themes**: {', '.join(creator_p.content_themes)}")
        with col_meta2:
            st.markdown(f"**Contact Email**: `{creator_p.contact_email}`")
            email_ready = creator_p.contact_email != "Not Found"
            st.markdown(f"**Email Outreach Ready**: `{'✅ YES' if email_ready else '⚠️ NO (DM Required)'}`")

        # Action: Generate/Regenerate
        engine = PersonalizationEngine(db=db)

        # Check existing saved messages
        saved_email = db.get_latest_generated_message(creator_p.id, "email")
        saved_dm = db.get_latest_generated_message(creator_p.id, "instagram_dm")

        btn_col1, btn_col2 = st.columns([1, 4])
        with btn_col1:
            if st.button("✨ Generate / Refresh Pitches"):
                with st.spinner("Formulating personalized pitches..."):
                    engine.generate_messages(creator_p, persist=True)
                    st.success("Pitches generated and saved!")
                    st.rerun()

        st.markdown("---")

        p_col1, p_col2 = st.columns(2)

        # 1. Email Collaboration Pitch
        with p_col1:
            st.markdown("### 📧 Email Collaboration Pitch (60–90 words)")
            if saved_email:
                subj = saved_email.get("subject", "Partnership Inquiry")
                body = saved_email.get("message_body", "")
                method = saved_email.get("generation_method", "unknown")
                wc = saved_email.get("word_count", 0)

                is_valid, reason, _ = validate_email_pitch(body)
                badge_color = "green" if is_valid else "red"

                st.markdown(f"**Subject Line**: `{subj}`")
                st.text_area("Email Body", body, height=220, key="txt_email_body")

                st.markdown(
                    f"**Word Count**: `:{badge_color}[{wc} words]` (Target: 60–90) | **Method**: `{method}`"
                )
                if not is_valid:
                    st.error(reason)
            else:
                st.info("No email pitch generated yet. Click 'Generate / Refresh Pitches' above.")

        # 2. Instagram DM
        with p_col2:
            st.markdown("### 📱 Instagram DM (15–30 words)")
            if saved_dm:
                dm_body = saved_dm.get("message_body", "")
                dm_method = saved_dm.get("generation_method", "unknown")
                dm_wc = saved_dm.get("word_count", 0)

                is_dm_valid, dm_reason, _ = validate_instagram_dm(dm_body)
                dm_badge_color = "green" if is_dm_valid else "red"

                st.text_area("Instagram DM Message", dm_body, height=120, key="txt_dm_body")
                st.markdown(
                    f"**Word Count**: `:{dm_badge_color}[{dm_wc} words]` (Target: 15–30) | **Method**: `{dm_method}`"
                )
                if not is_dm_valid:
                    st.error(dm_reason)
            else:
                st.info("No Instagram DM generated yet. Click 'Generate / Refresh Pitches' above.")


# Section 5: Outreach Tracker
elif view_mode == "🚀 Outreach Tracker":
    st.markdown('<div class="main-header">Outreach Dispatch & Deduplication Tracker</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Safely execute simulated outreach batches, log manual Instagram DMs, and verify duplicate protection.</div>', unsafe_allow_html=True)

    dispatcher = OutreachDispatcher(db=db)

    # Dispatch Actions Box
    st.markdown("### ⚙️ Dispatch Controls (Safe Simulation)")

    d_col1, d_col2 = st.columns(2)

    with d_col1:
        st.markdown("#### 📧 Batch Simulated Email Outreach")
        st.write("Executes simulated email delivery for all qualified creators with public emails.")
        if st.button("🚀 Run Simulated Email Batch (Safe)"):
            with st.spinner("Simulating email outreach batch..."):
                batch_res = dispatcher.dispatch_batch_simulated_emails()
                st.success(
                    f"Batch complete: {batch_res['simulated_dispatched']} simulated sends, "
                    f"{batch_res['skipped_duplicate']} skipped duplicates, "
                    f"{batch_res['skipped_no_email']} skipped (email missing)."
                )
                st.rerun()

    with d_col2:
        st.markdown("#### 📱 Manual Instagram DM Logging")
        st.write("Record a verified manual Instagram DM send (does not automate social APIs).")
        qualified_names = [
            p.name for p in influencers
            if p.id in audits_by_id and audits_by_id[p.id].classification == "QUALIFIED"
        ]
        if qualified_names:
            dm_creator_name = st.selectbox("Select Creator for Manual DM", qualified_names, key="sel_dm_creator")
            target_p = next(p for p in influencers if p.name == dm_creator_name)
            saved_dm_rec = db.get_latest_generated_message(target_p.id, "instagram_dm")
            default_dm = saved_dm_rec["message_body"] if saved_dm_rec else f"Hey {target_p.name.split()[0]}! Loved your work and would love to collaborate."
            dm_input = st.text_input("DM Message Text", default_dm)

            if st.button("✍️ Record as Manually Sent"):
                success, msg, _ = dispatcher.record_manual_instagram_dm(target_p, dm_input, simulated=False)
                if success:
                    st.success(msg)
                else:
                    st.warning(msg)
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Outreach History Log")

    # Fetch all outreach logs
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT * FROM outreach_logs ORDER BY timestamp DESC")
        raw_logs = cursor.fetchall()

    if raw_logs:
        log_records = []
        for r in raw_logs:
            p_match = next((p for p in influencers if p.id == r["influencer_id"]), None)
            log_records.append({
                "Timestamp (UTC)": r["timestamp"][:19],
                "Creator Name": p_match.name if p_match else r["influencer_id"],
                "Channel": r["channel"].upper(),
                "Recipient": r["recipient_contact"],
                "Status": r["status"],
                "Subject": r["subject"] or "N/A",
                "Message Preview": r["message_body"][:70] + "...",
                "Deduplication Key": r["deduplication_key"],
            })

        df_logs = pd.DataFrame(log_records)
        st.dataframe(df_logs, use_container_width=True)
    else:
        st.info("No outreach logs recorded yet. Execute a simulated dispatch above.")


# Section 6: Data Import & Export
elif view_mode == "📁 Import & Export":
    st.markdown('<div class="main-header">Data Import & Export Center</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Ingest user-supplied CSV/JSON creator profiles or export project artifacts.</div>', unsafe_allow_html=True)

    c_imp, c_exp = st.columns(2)

    with c_imp:
        st.subheader("📥 Ingest Creator Dataset")
        uploaded_file = st.file_uploader("Upload CSV or JSON dataset", type=["csv", "json"])

        if uploaded_file is not None:
            # Save temporarily and import
            temp_path = Path(f"data/temp_upload_{uploaded_file.name}")
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            source = SeedFileDiscoverySource()
            try:
                imported_profiles = source.discover(file_path=temp_path, allow_fictional=False)
                st.info(f"Loaded {len(imported_profiles)} valid profiles from uploaded file.")

                if st.button("Confirm Ingestion into SQLite Database"):
                    ins = 0
                    dup = 0
                    for p in imported_profiles:
                        if db.insert_influencer(p):
                            ins += 1
                        else:
                            dup += 1
                    st.success(f"Import complete: {ins} inserted, {dup} duplicates skipped.")
                    temp_path.unlink(missing_ok=True)
                    st.rerun()
            except Exception as e:
                st.error(f"Error reading file: {e}")
                temp_path.unlink(missing_ok=True)

    with c_exp:
        st.subheader("📤 Export Data Artifacts")
        st.write("Export complete database tables as structured CSV reports:")

        if influencers:
            # Profiles export
            df_all_profs = pd.DataFrame([p.model_dump() for p in influencers])
            st.download_button(
                "📥 Export Influencers CSV",
                data=df_all_profs.to_csv(index=False).encode("utf-8"),
                file_name="all_influencers.csv",
                mime="text/csv",
            )

        # Outreach logs export
        with db.get_connection() as conn:
            logs_cursor = conn.execute("SELECT * FROM outreach_logs ORDER BY timestamp DESC")
            all_logs = [dict(r) for r in logs_cursor.fetchall()]

        if all_logs:
            df_all_logs = pd.DataFrame(all_logs)
            st.download_button(
                "📥 Export Outreach Logs CSV",
                data=df_all_logs.to_csv(index=False).encode("utf-8"),
                file_name="outreach_logs.csv",
                mime="text/csv",
            )

