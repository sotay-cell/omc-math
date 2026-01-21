import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import json
import datetime
import pytz
import requests
import urllib.parse

# --- ページ設定 ---
st.set_page_config(page_title="Math Contest DX", layout="wide")
JST = pytz.timezone('Asia/Tokyo')

# --- 0. 認証機能 (OAuth) ---
def google_login():
    """Googleログインを行い、メールアドレスと名前を返す"""
    # Secretsから設定取得
    try:
        client_id = st.secrets["oauth"]["client_id"]
        client_secret = st.secrets["oauth"]["client_secret"]
        redirect_uri = st.secrets["oauth"]["redirect_uri"]
    except:
        st.error("Secretsに [oauth] 設定がありません。")
        return None, None

    # URLパラメータに 'code' があるか確認（Googleからの戻り）
    auth_code = st.query_params.get("code")

    if auth_code:
        # 2回目以降の自動リロード対策（コードを消費したら消す）
        st.query_params.clear()
        
        # 1. 認可コードをトークンに交換
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "code": auth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        r = requests.post(token_url, data=data)
        if r.status_code != 200:
            st.error("ログイン失敗: トークン交換エラー")
            return None, None
        
        token_info = r.json()
        access_token = token_info.get("access_token")

        # 2. ユーザー情報を取得
        user_url = "https://www.googleapis.com/oauth2/v1/userinfo"
        headers = {"Authorization": f"Bearer {access_token}"}
        user_r = requests.get(user_url, headers=headers)
        if user_r.status_code != 200:
            st.error("ユーザー情報取得エラー")
            return None, None
            
        user_data = user_r.json()
        email = user_data.get("email")
        name = user_data.get("name")
        
        # セッションに保存
        st.session_state["user_email"] = email
        st.session_state["user_name"] = name
        st.rerun() # 再読み込みして画面切り替え

    # ログイン済みなら情報を返す
    if "user_email" in st.session_state:
        return st.session_state["user_email"], st.session_state["user_name"]

    # まだならログインURLを生成してリンクを表示
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "email profile",
        "access_type": "online",
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    
    st.markdown(f"""
        <div style="text-align:center; margin-top: 50px;">
            <h1>🏆 Math Contest Login</h1>
            <p>参加するにはGoogleアカウントでログインしてください</p>
            <a href="{auth_url}" target="_self">
                <button style="
                    background-color: #4285F4; color: white; border: none; 
                    padding: 12px 24px; font-size: 16px; border-radius: 5px; cursor: pointer;
                    display: flex; align-items: center; margin: 0 auto; gap: 10px;">
                    <img src="https://upload.wikimedia.org/wikipedia/commons/5/53/Google_%22G%22_Logo.svg" width="20">
                    Googleでログイン
                </button>
            </a>
        </div>
    """, unsafe_allow_html=True)
    return None, None

# --- 1. データベース接続 ---
@st.cache_resource
def get_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name('secrets.json', scope)
        client = gspread.authorize(creds)
        sh = client.open("omc_db")
        try: ws_prob = sh.worksheet("problems")
        except: ws_prob = sh.add_worksheet(title="problems", rows="100", cols="20")
        return sh.sheet1, ws_prob
    except: return None, None

@st.cache_data(ttl=5)
def fetch_ranking_data():
    sheet_rank, _ = get_connection()
    return sheet_rank.get_all_records() if sheet_rank else []

# --- 実行開始 ---
# まずログインチェック
user_email, user_name = google_login()

# ログインしていない場合はここでストップ（画面にはログインボタンのみ表示）
if not user_email:
    st.stop()

# --- 以下、ログイン後の世界 ---
sheet_rank, sheet_prob = get_connection()
if sheet_rank is None:
    st.error("DB接続エラー")
    st.stop()

# サイドバーにユーザー情報表示
with st.sidebar:
    st.write(f"👤 **{user_name}**")
    st.caption(f"{user_email}")
    if st.button("ログアウト"):
        st.session_state.clear()
        st.rerun()

# --- 2. 管理パネル ---
admin_mode = False
# 特定のメールアドレスだけを管理者にしたい場合はここで判定可能
# 例: if user_email == "teacher@school.ed.jp":
with st.sidebar.expander("👮 管理者メニュー"):
    admin_pass = st.text_input("パスワード", type="password")
    if admin_pass == "admin123":
        admin_mode = True
        st.success("認証成功")
        tab_ctrl, tab_make = st.tabs(["🎮 開催操作", "📝 問題作成"])
        
        with tab_ctrl:
            new_cid = st.text_input("開催ID", value="A001")
            duration_min = st.number_input("時間(分)", min_value=1, value=30)
            c1, c2, c3 = st.columns(3)
            if c1.button("▶ 開始"):
                now = datetime.datetime.now(JST)
                end_time = now + datetime.timedelta(minutes=duration_min)
                sheet_rank.update_acell('D1', '開催中')
                sheet_rank.update_acell('E1', new_cid)
                sheet_rank.update_acell('F1', end_time.strftime('%Y-%m-%d %H:%M:%S'))
                st.toast("開始しました")
                time.sleep(1)
                st.rerun()
            if c2.button("⏹ 終了"):
                sheet_rank.update_acell('D1', '終了')
                st.toast("終了しました")
                st.rerun()
            if c3.button("🗑 リセット"):
                all_rows = sheet_rank.get_all_values()
                if len(all_rows) > 1: sheet_rank.batch_clear([f"A2:D{len(all_rows)}"])
                st.toast("リセット完了")

        with tab_make:
            st.write("###### 問題追加")
            in_cid = st.text_input("ID", value=new_cid)
            in_no = st.number_input("No.", min_value=1, value=1)
            in_pt = st.number_input("Pt", step=100, value=100)
            in_ans = st.text_input("正解")
            in_q = st.text_area("問題文 ($...$)", height=100)
            st.caption("プレビュー:")
            if in_q: st.markdown(in_q)
            if st.button("追加"):
                sheet_prob.append_row([in_cid, in_no, in_q, in_ans, in_pt])
                st.success("追加しました")

# --- 3. データ読み込み ---
try:
    vals = sheet_rank.get('D1:F1')
    status = vals[0][0] if vals and len(vals[0])>0 else "待機中"
    active_cid = str(vals[0][1]) if vals and len(vals[0])>1 else "1"
    end_time_str = vals[0][2] if vals and len(vals[0])>2 else ""
except:
    status, active_cid, end_time_str = "待機中", "1", ""

remaining_msg, is_time_up = "", False
if status == "開催中" and end_time_str:
    try:
        end_dt = JST.localize(datetime.datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S'))
        diff = end_dt - datetime.datetime.now(JST)
        if diff.total_seconds() > 0:
            mm, ss = divmod(int(diff.total_seconds()), 60)
            remaining_msg = f"⏱ 残り: {mm}分 {ss}秒"
        else:
            remaining_msg, is_time_up = "⏱ タイムアップ！", True
    except: pass

try:
    prob_data = sheet_prob.get_all_records()
    df_prob = pd.DataFrame(prob_data)
    if not df_prob.empty and 'contest_id' in df_prob.columns:
        df_prob['contest_id'] = df_prob['contest_id'].astype(str)
        current_problems = df_prob[df_prob['contest_id'] == active_cid].sort_values('id')
    else: current_problems = pd.DataFrame()
except: current_problems = pd.DataFrame()

# --- 4. ユーザーデータ処理 ---
# ログイン名(user_name)をそのまま使う
if "wa_lock" not in st.session_state: st.session_state["wa_lock"] = {}

raw_rank_data = fetch_ranking_data()
df_rank = pd.DataFrame(raw_rank_data)
score, solved = 0, []

if not df_rank.empty and user_name in df_rank['user'].values:
    row = df_rank[df_rank['user'] == user_name].iloc[0]
    score = int(row['score'])
    solved = str(row['solved_history']).split(',') if str(row['solved_history']) else []
else:
    if status != "待機中":
        # Google名を登録
        sheet_rank.append_row([user_name, 0, "", ""])
        fetch_ranking_data.clear()
        st.rerun()

solver_counts = {}
if not df_rank.empty:
    for h in df_rank['solved_history']:
        for i in str(h).split(','): 
            if i: solver_counts[i] = solver_counts.get(i, 0) + 1

@st.fragment(run_every=5)
def auto_ranking_table():
    st.write("### 🏆 順位表 (LIVE)")
    live_data = fetch_ranking_data()
    df_live = pd.DataFrame(live_data)
    if not df_live.empty:
        view_df = df_live[['user', 'score']].sort_values('score', ascending=False).reset_index(drop=True)
        view_df.index += 1
        st.dataframe(view_df, use_container_width=True)
    else: st.write("データなし")

st.title("🏆 リアルタイム数学コンテスト DX")

# --- 5. メイン画面 ---
if status == "開催中":
    if is_time_up: st.error("⏰ 終了！")
    else: st.info(f"🔥 開催中 | {remaining_msg}")

if status == "待機中":
    st.info(f"⏳ 第{active_cid}回: 準備中...")
    auto_ranking_table()

elif status == "開催中":
    c1, c2 = st.columns([3, 1])
    c1.metric(f"Score", score)
    if c2.button("手動更新"): st.rerun()
    
    col_q, col_r = st.columns([2, 1])
    with col_q:
        if current_problems.empty: st.warning("問題なし")
        for i, row in current_problems.iterrows():
            pid, uid = str(row['id']), f"{active_cid}_{str(row['id'])}"
            solvers = solver_counts.get(uid, 0)
            if uid in solved:
                st.success(f"✅ Q{pid} クリア！")
            else:
                lock_rem = st.session_state["wa_lock"].get(uid, 0) - time.time()
                with st.expander(f"Q{pid} ({row['pt']}点) - 正解: {solvers}人"):
                    st.markdown(row['q'])
                    if is_time_up: st.write("🚫 終了")
                    elif lock_rem > 0: st.error(f"❌ WA: あと{int(lock_rem)}秒")
                    else:
                        ans = st.text_input("回答", key=f"in_{uid}")
                        if st.button("送信", key=f"btn_{uid}"):
                            if str(ans).strip() == str(row['ans']):
                                st.balloons()
                                try:
                                    cell = sheet_rank.find(user_name)
                                    cur_s = int(sheet_rank.cell(cell.row, 2).value)
                                    cur_h = sheet_rank.cell(cell.row, 3).value
                                    new_h = (cur_h + "," + uid) if cur_h else uid
                                    sheet_rank.update_cell(cell.row, 2, cur_s + row['pt'])
                                    sheet_rank.update_cell(cell.row, 3, new_h)
                                    fetch_ranking_data.clear()
                                    st.rerun()
                                except: st.error("通信エラー")
                            else:
                                st.error("不正解...")
                                st.session_state["wa_lock"][uid] = time.time() + 10
                                st.rerun()
    with col_r:
        auto_ranking_table()

elif status == "終了":
    st.warning("終了")
    auto_ranking_table()
