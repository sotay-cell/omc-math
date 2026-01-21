import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import json

st.set_page_config(page_title="Math Contest", layout="wide")

# --- 1. データベース接続（最強の裏技版） ---
@st.cache_resource
def get_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    try:
        # パターンA: Streamlit Cloud (丸ごと貼り付け版)
        if "gcp_json" in st.secrets:
            # 文字列として読み込んで、ここでJSONに戻す（これが一番確実）
            key_dict = json.loads(st.secrets["gcp_json"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
        
        # パターンB: 従来のSecrets書き方（念のため残す）
        elif "gcp_service_account" in st.secrets:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
            
        # パターンC: ローカルファイル
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name('secrets.json', scope)

        client = gspread.authorize(creds)
        sh = client.open("omc_db")
        return sh.sheet1, sh.worksheet("problems")

    except Exception as e:
        # 具体的なエラーを表示する（デバッグ用）
        st.error(f"💣 接続エラー発生: {e}")
        return None, None

# タイトル
st.title("🏆 リアルタイム数学コンテスト")

# 接続実行
sheet_rank, sheet_prob = get_connection()

if sheet_rank is None:
    st.error("設定を確認してください。Secretsに `gcp_json` はありますか？")
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

# --- 3. ログインと表示 ---
user_name = st.sidebar.text_input("ニックネーム", key="login")
if not user_name:
    st.info("👈 名前を入力してください")
    st.stop()

# ユーザー処理
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

# 画面切り替え
if status == "待機中":
    st.info("⏳ 待機中...")
    if st.button("更新"): st.rerun()

elif status == "開催中":
    st.metric(f"Score ({active_cid})", score)
    if st.button("更新"): st.rerun()
    
    col1, col2 = st.columns([2,1])
    with col1:
        if current_problems.empty:
            st.warning("問題がありません")
        for i, row in current_problems.iterrows():
            uid = f"{active_cid}_{row['id']}"
            if uid in solved:
                st.info(f"✅ Q{row['id']} クリア")
            else:
                with st.expander(f"Q{row['id']} ({row['pt']}点)"):
                    st.latex(row['q'])
                    if st.button("送信", key=f"b_{uid}"):
                        ans = st.text_input("答", key=f"a_{uid}") # 簡略化のためここ注意
                        # 実際はinputとbuttonを分ける必要がありますが、簡易版として
                        pass 
                    # フォーム修正: inputを外に出す
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
    with col2:
        st.write("順位表")
        st.dataframe(df_rank[['user', 'score']].sort_values('score', ascending=False), use_container_width=True)

elif status == "終了":
    st.warning("終了")
    st.dataframe(df_rank[['user', 'score']].sort_values('score', ascending=False))
