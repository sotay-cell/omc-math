import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import json

# --- ページ設定 ---
st.set_page_config(page_title="Math Contest", layout="wide")

# --- 1. データベース接続（重要：Secrets対応） ---
@st.cache_resource
def get_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # Cloud (Secrets) 優先、なければ Local (jsonファイル)
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name('secrets.json', scope)
        except:
            return None, None
            
    client = gspread.authorize(creds)
    sh = client.open("omc_db")
    # シート取得（エラー処理付き）
    try:
        ws_prob = sh.worksheet("problems")
    except:
        ws_prob = sh.add_worksheet(title="problems", rows="100", cols="20")
        
    return sh.sheet1, ws_prob

# タイトル
st.title("🏆 リアルタイム数学コンテスト")

sheet_rank, sheet_prob = get_connection()
if sheet_rank is None:
    st.error("🚨 エラー: データベース接続に失敗しました。Secretsの設定を確認してください。")
    st.stop()

# --- 2. 設定と問題の読み込み ---
try:
    raw_status = sheet_rank.acell('D1').value
    status = raw_status if raw_status else "待機中"
    
    raw_cid = sheet_rank.acell('E1').value
    active_cid = str(raw_cid) if raw_cid else "1"
except:
    status = "待機中"
    active_cid = "1"

# 問題データを取得
try:
    prob_data = sheet_prob.get_all_records()
    df_prob = pd.DataFrame(prob_data)
    
    if not df_prob.empty and 'contest_id' in df_prob.columns:
        df_prob['contest_id'] = df_prob['contest_id'].astype(str)
        current_problems = df_prob[df_prob['contest_id'] == active_cid].sort_values('id')
    else:
        current_problems = pd.DataFrame()
except:
    current_problems = pd.DataFrame()

# --- 3. ユーザーログイン ---
user_name = st.sidebar.text_input("ニックネームを入力", key="login_name")
if not user_name:
    st.warning("👈 左のサイドバーで名前を入力して参加してください。")
    st.stop()

# --- 4. ユーザーデータ処理 ---
data = sheet_rank.get_all_records()
df_rank = pd.DataFrame(data)

if not df_rank.empty and user_name in df_rank['user'].values:
    my_record = df_rank[df_rank['user'] == user_name].iloc[0]
    current_score = int(my_record['score'])
    solved_raw = str(my_record['solved_history'])
    solved_list = solved_raw.split(',') if solved_raw else []
else:
    new_row = [user_name, 0, "", ""]
    sheet_rank.append_row(new_row)
    current_score = 0
    solved_list = []
    st.toast(f"ようこそ、{user_name}さん！")

# --- 5. 画面表示 ---
if status == "待機中":
    st.info(f"⏳ 第{active_cid}回コンテスト: 準備中...")
    if not df_rank.empty:
        st.write("参加者リスト:")
        st.dataframe(df_rank[['user', 'score']], hide_index=True)
    if st.button("更新"):
        st.rerun()

elif status == "開催中":
    c1, c2, c3 = st.columns([2,1,1])
    c1.success(f"🔥 第{active_cid}回 コンテスト開催中！")
    c2.metric("SCORE", f"{current_score}")
    if c3.button("更新"):
        st.rerun()

    col_q, col_r = st.columns([2, 1])

    with col_q:
        if current_problems.empty:
            st.warning(f"ID「{active_cid}」の問題がありません。problemsシートを確認してください。")
        
        for index, row in current_problems.iterrows():
            pid = str(row['id'])
            unique_pid = f"{active_cid}_{pid}"
            
            if unique_pid in solved_list:
                st.info(f"✅ 第{pid}問 - クリア！")
            else:
                with st.expander(f"第{pid}問 ({row['pt']}点)"):
                    st.latex(row['q'])
                    ans_input = st.text_input("回答", key=f"q_{unique_pid}")
                    if st.button("送信", key=f"b_{unique_pid}"):
                        if str(ans_input).strip() == str(row['ans']):
                            st.balloons()
                            cell = sheet_rank.find(user_name)
                            new_score = current_score + row['pt']
                            new_history_list = solved_list + [unique_pid]
                            sheet_rank.update_cell(cell.row, 2, new_score)
                            sheet_rank.update_cell(cell.row, 3, ",".join(new_history_list))
                            st.success("正解！")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("不正解...")

    with col_r:
        st.write("### 🏆 Standings")
        if not df_rank.empty:
            rank_view = df_rank[['user', 'score']].sort_values('score', ascending=False).reset_index(drop=True)
            rank_view.index += 1
            st.dataframe(rank_view, use_container_width=True)

elif status == "終了":
    st.warning("🏁 コンテスト終了")
    if not df_rank.empty:
        rank_view = df_rank[['user', 'score']].sort_values('score', ascending=False).reset_index(drop=True)
        rank_view.index += 1
        st.dataframe(rank_view)
