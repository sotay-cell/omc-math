import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import json

# --- ページ設定 ---
st.set_page_config(page_title="Math Contest", layout="wide")

# --- 1. データベース接続（標準版） ---
@st.cache_resource
def get_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # Secretsから認証情報を読み込む（標準的なTOML形式）
    if "gcp_service_account" in st.secrets:
        # 辞書型に変換して渡す
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        # ローカル/Colab用のフォールバック
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name('secrets.json', scope)
        except:
            return None, None

    client = gspread.authorize(creds)
    sh = client.open("omc_db")
    
    # problemsシートがなければ作る、あれば読み込む
    try:
        ws_prob = sh.worksheet("problems")
    except:
        ws_prob = sh.add_worksheet(title="problems", rows="100", cols="20")
        
    return sh.sheet1, ws_prob

# タイトル
st.title("🏆 リアルタイム数学コンテスト")

sheet_rank, sheet_prob = get_connection()

if sheet_rank is None:
    st.error("🚨 接続エラー: Secretsの設定を確認してください。")
    st.info("ヒント: Streamlit CloudのSecretsには [gcp_service_account] 形式で保存してください。")
    st.stop()

# --- 2. 設定読み込み ---
try:
    status = sheet_rank.acell('D1').value or "待機中"
    active_cid = str(sheet_rank.acell('E1').value or "1")
except:
    status = "待機中"
    active_cid = "1"

# 問題データ取得
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

# --- 3. ログイン機能 ---
user_name = st.sidebar.text_input("ニックネーム", key="login")
if not user_name:
    st.warning("👈 左のサイドバーで名前を入力して参加してください。")
    st.stop()

# ユーザーデータ処理
df_rank = pd.DataFrame(sheet_rank.get_all_records())
if not df_rank.empty and user_name in df_rank['user'].values:
    row = df_rank[df_rank['user'] == user_name].iloc[0]
    score = int(row['score'])
    solved = str(row['solved_history']).split(',') if str(row['solved_history']) else []
else:
    sheet_rank.append_row([user_name, 0, "", ""])
    score = 0
    solved = []
    st.toast(f"Welcome {user_name}!")

# --- 4. 画面表示 ---
if status == "待機中":
    st.info(f"⏳ 第{active_cid}回コンテスト: 待機中...")
    if st.button("更新"): st.rerun()

elif status == "開催中":
    c1, c2 = st.columns([3, 1])
    c1.metric(f"Score (Round {active_cid})", score)
    if c2.button("更新"): st.rerun()
    
    col_q, col_r = st.columns([2, 1])
    with col_q:
        if current_problems.empty:
            st.warning("問題データがありません。")
        for i, row in current_problems.iterrows():
            uid = f"{active_cid}_{row['id']}"
            if uid in solved:
                st.info(f"✅ Q{row['id']} クリア！")
            else:
                with st.expander(f"Q{row['id']} ({row['pt']}点)"):
                    st.latex(row['q'])
                    ans = st.text_input("回答", key=f"in_{uid}")
                    if st.button("送信", key=f"btn_{uid}"):
                        if str(ans) == str(row['ans']):
                            st.balloons()
                            cell = sheet_rank.find(user_name)
                            sheet_rank.update_cell(cell.row, 2, score + row['pt'])
                            sheet_rank.update_cell(cell.row, 3, ",".join(solved + [uid]))
                            st.rerun()
                        else:
                            st.error("不正解")
    with col_r:
        st.write("### 順位表")
        st.dataframe(df_rank[['user', 'score']].sort_values('score', ascending=False), use_container_width=True)

elif status == "終了":
    st.warning("終了しました")
    st.dataframe(df_rank[['user', 'score']].sort_values('score', ascending=False))
