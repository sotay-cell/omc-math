import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import datetime
import pytz

# --- ページ設定 ---
st.set_page_config(page_title="Math Contest Pro", layout="wide")
JST = pytz.timezone('Asia/Tokyo')

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
        
        # シート接続（なければ作るエラー回避）
        try: ws_users = sh.worksheet("users")
        except: ws_users = sh.add_worksheet("users", 100, 5)
        
        try: ws_settings = sh.worksheet("settings")
        except: ws_settings = sh.add_worksheet("settings", 10, 5)
        
        try: ws_prob = sh.worksheet("problems")
        except: ws_prob = sh.add_worksheet("problems", 100, 5)
            
        return ws_users, ws_settings, ws_prob
    except Exception as e: return None, None, None

@st.cache_data(ttl=5)
def fetch_data():
    """データ取得用（5秒キャッシュ）"""
    ws_users, ws_settings, _ = get_connection()
    if not ws_users: return [], {}
    
    # ユーザーデータ
    users = ws_users.get_all_records()
    
    # 設定データ（A列がキー、B列が値と想定）
    settings_raw = ws_settings.get_all_values()
    settings = {row[0]: row[1] for row in settings_raw if len(row) >= 2}
    
    return users, settings

# --- メイン処理開始 ---
ws_users, ws_settings, ws_prob = get_connection()
if not ws_users:
    st.error("🚨 データベース接続エラー: シート名が正しいか確認してください (users, settings, problems)")
    st.stop()

st.title("🏆 リアルタイム数学コンテスト Pro")

# --- 2. ログイン処理 (ID/Pass方式) ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["my_id"] = ""

# ログアウト機能
if st.sidebar.button("ログアウト") if st.session_state["logged_in"] else False:
    st.session_state["logged_in"] = False
    st.rerun()

# ログイン画面
if not st.session_state["logged_in"]:
    st.markdown("##### 🔐 生徒ログイン")
    with st.form("login_form"):
        input_id = st.text_input("ユーザーID")
        input_pass = st.text_input("パスワード", type="password")
        submitted = st.form_submit_button("ログイン")
        
        if submitted:
            # マスタデータ取得（キャッシュを使わず最新を見る）
            users_data = ws_users.get_all_records()
            # ID検索
            user_found = False
            for u in users_data:
                # 文字列として比較
                if str(u.get('user_id')) == str(input_id) and str(u.get('password')) == str(input_pass):
                    st.session_state["logged_in"] = True
                    st.session_state["my_id"] = str(input_id)
                    user_found = True
                    break
            
            if user_found:
                st.success(f"ログイン成功！ようこそ {input_id} さん")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("IDまたはパスワードが間違っています。")
    
    # ここでストップ（ログインしないと中身は見せない）
    st.stop()

# --- 3. ログイン後の世界 ---
my_id = st.session_state["my_id"]

# データ再取得
users_list, settings_dict = fetch_data()
df_users = pd.DataFrame(users_list)

# 自分のデータ特定
if not df_users.empty and 'user_id' in df_users.columns:
    # 型変換して検索
    df_users['user_id'] = df_users['user_id'].astype(str)
    my_row = df_users[df_users['user_id'] == my_id]
    if not my_row.empty:
        my_score = int(my_row.iloc[0]['score'])
        my_hist_str = str(my_row.iloc[0]['history'])
        my_solved = my_hist_str.split(',') if my_hist_str else []
    else:
        st.error("データエラー：あなたのIDが見つかりません")
        st.stop()
else:
    my_score = 0
    my_solved = []

# 設定値の取り出し
status = settings_dict.get("status", "待機中")
active_cid = settings_dict.get("contest_id", "A001")
end_time_str = settings_dict.get("end_time", "")

# タイマー計算
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

# 問題取得
try:
    prob_data = ws_prob.get_all_records()
    df_prob = pd.DataFrame(prob_data)
    if not df_prob.empty and 'contest_id' in df_prob.columns:
        df_prob['contest_id'] = df_prob['contest_id'].astype(str)
        current_problems = df_prob[df_prob['contest_id'] == active_cid].sort_values('id')
    else: current_problems = pd.DataFrame()
except: current_problems = pd.DataFrame()

# 正解者数カウント
solver_counts = {}
if 'history' in df_users.columns:
    for h in df_users['history']:
        for i in str(h).split(','): 
            if i: solver_counts[i] = solver_counts.get(i, 0) + 1

# --- 4. 管理者メニュー (パスワード: admin123) ---
with st.sidebar.expander("👮 管理者メニュー"):
    admin_pass = st.text_input("Admin Pass", type="password")
    if admin_pass == "admin123":
        tab_c, tab_m, tab_u = st.tabs(["開催", "作問", "生徒"])
        
        # 開催管理
        with tab_c:
            new_cid = st.text_input("ID", value=active_cid)
            min_val = st.number_input("分", value=30)
            c1, c2, c3 = st.columns(3)
            if c1.button("開始"):
                et = datetime.datetime.now(JST) + datetime.timedelta(minutes=min_val)
                ws_settings.update_acell('B1', '開催中')
                ws_settings.update_acell('B2', new_cid)
                ws_settings.update_acell('B3', et.strftime('%Y-%m-%d %H:%M:%S'))
                st.toast("開始")
                time.sleep(1)
                st.rerun()
            if c2.button("終了"):
                ws_settings.update_acell('B1', '終了')
                st.rerun()
            if c3.button("成績リセット"):
                # 全員のscore(C列)とhistory(D列)をクリア
                # ユーザー数分だけループして0にする（行削除はしない）
                users_len = len(users_list)
                if users_len > 0:
                    # 2行目から users_len+1 行目までの C, D列を書き換え
                    cell_list = []
                    for r in range(2, users_len + 2):
                        cell_list.append(gspread.Cell(r, 3, 0))  # score
                        cell_list.append(gspread.Cell(r, 4, "")) # history
                    ws_users.update_cells(cell_list)
                    st.toast("リセット完了")

        # 問題作成
        with tab_m:
            in_q = st.text_area("問題文", height=60)
            in_a = st.text_input("正解")
            in_p = st.number_input("点", value=100)
            in_no = st.number_input("No", value=1)
            if st.button("追加"):
                ws_prob.append_row([new_cid, in_no, in_q, in_a, in_p])
                st.success("追加済")
        
        # 生徒登録（簡易）
        with tab_u:
            new_uid = st.text_input("新規ID")
            new_upass = st.text_input("新規Pass")
            if st.button("生徒登録"):
                ws_users.append_row([new_uid, new_upass, 0, ""])
                st.success(f"{new_uid} を登録しました")

# --- 5. 自動更新ランキング ---
@st.fragment(run_every=5)
def show_ranking():
    st.write("### 🏆 Standings")
    u, _ = fetch_data()
    df = pd.DataFrame(u)
    if not df.empty:
        df['score'] = pd.to_numeric(df['score'], errors='coerce').fillna(0)
        view = df[['user_id', 'score']].sort_values('score', ascending=False).reset_index(drop=True)
        view.index += 1
        st.dataframe(view, use_container_width=True)

# --- 6. メイン画面 ---
if status == "開催中":
    st.info(f"🔥 {active_cid} 開催中 | {remaining_msg}")
elif status == "待機中":
    st.info("⏳ 待機中...")
    show_ranking()

if status == "開催中":
    if is_time_up: st.error("⏰ 終了")
    
    col_main, col_rank = st.columns([2, 1])
    
    with col_main:
        st.metric(f"My Score ({my_id})", my_score)
        if st.button("手動更新"): st.rerun()
        
        if "wa_lock" not in st.session_state: st.session_state["wa_lock"] = {}
        
        for i, row in current_problems.iterrows():
            pid = str(row['id'])
            uid = f"{active_cid}_{pid}"
            solvers = solver_counts.get(uid, 0)
            
            if uid in my_solved:
                st.success(f"✅ Q{pid} クリア")
            else:
                lock = st.session_state["wa_lock"].get(uid, 0) - time.time()
                with st.expander(f"Q{pid} ({row['pt']}点) - 正解{solvers}人"):
                    st.markdown(row['q'])
                    if not is_time_up:
                        if lock > 0:
                            st.error(f"❌ WA: あと{int(lock)}秒")
                        else:
                            ans = st.text_input("回答", key=f"ans_{uid}")
                            if st.button("送信", key=f"btn_{uid}"):
                                if str(ans).strip() == str(row['ans']):
                                    # 正解処理
                                    try:
                                        # 生徒の行を探す
                                        cell = ws_users.find(my_id) # IDで検索
                                        # 現在値取得
                                        cur_s = int(ws_users.cell(cell.row, 3).value)
                                        cur_h = ws_users.cell(cell.row, 4).value
                                        new_h = (cur_h + "," + uid) if cur_h else uid
                                        
                                        ws_users.update_cell(cell.row, 3, cur_s + row['pt'])
                                        ws_users.update_cell(cell.row, 4, new_h)
                                        
                                        fetch_data.clear()
                                        st.toast("正解！")
                                        time.sleep(0.5)
                                        st.rerun()
                                    except:
                                        st.error("通信エラー")
                                else:
                                    st.error("不正解")
                                    st.session_state["wa_lock"][uid] = time.time() + 10
                                    st.rerun()

    with col_rank:
        show_ranking()

elif status == "終了":
    st.warning("終了しました")
    show_ranking()
