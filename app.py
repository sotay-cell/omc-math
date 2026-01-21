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
    ws_users, ws_settings, ws_prob = get_connection()
    if not ws_users: return [], {}, []
    
    users = ws_users.get_all_records()
    settings_raw = ws_settings.get_all_values()
    settings = {row[0]: row[1] for row in settings_raw if len(row) >= 2}
    prob_data = ws_prob.get_all_records() # 問題データも取得してIDリストを作る
    return users, settings, prob_data

# --- メイン処理開始 ---
ws_users, ws_settings, ws_prob = get_connection()
if not ws_users:
    st.error("🚨 データベース接続エラー: シート名を確認してください")
    st.stop()

st.title("🏆 リアルタイム数学コンテスト Pro")

# データ読み込み
users_list, settings_dict, prob_list = fetch_data()

# ==========================================
# 👮 管理者メニュー
# ==========================================
status = settings_dict.get("status", "待機中")
active_cid = settings_dict.get("contest_id", "A001")
end_time_str = settings_dict.get("end_time", "")

# 既存のコンテストIDリストを作成（重複なし）
existing_cids = sorted(list(set([str(p['contest_id']) for p in prob_list if 'contest_id' in p])))
if active_cid not in existing_cids:
    existing_cids.append(active_cid) # 現在の設定IDも含める

with st.sidebar.expander("👮 管理者メニュー"):
    admin_pass = st.text_input("Admin Pass", type="password")
    if admin_pass == "admin123":
        tab_c, tab_m, tab_u = st.tabs(["開催", "作問", "生徒"])
        
        # 開催管理
        with tab_c:
            st.write(f"Status: **{status}**")
            # 既存IDから選択、または手入力
            cid_selection = st.selectbox("開催するIDを選択", options=existing_cids + ["(新規入力)"], index=0 if active_cid in existing_cids else len(existing_cids))
            
            if cid_selection == "(新規入力)":
                target_cid = st.text_input("新しいIDを入力", value=active_cid)
            else:
                target_cid = cid_selection

            min_val = st.number_input("制限時間(分)", value=30)
            c1, c2, c3 = st.columns(3)
            if c1.button("開始"):
                et = datetime.datetime.now(JST) + datetime.timedelta(minutes=min_val)
                ws_settings.update_acell('B1', '開催中')
                ws_settings.update_acell('B2', target_cid)
                ws_settings.update_acell('B3', et.strftime('%Y-%m-%d %H:%M:%S'))
                st.toast("開始")
                time.sleep(1)
                st.rerun()
            if c2.button("終了"):
                ws_settings.update_acell('B1', '終了')
                st.rerun()
            if c3.button("成績リセット"):
                users_len = len(users_list)
                if users_len > 0:
                    cell_list = []
                    for r in range(2, users_len + 2):
                        cell_list.append(gspread.Cell(r, 4, 0))  # score
                        cell_list.append(gspread.Cell(r, 5, "")) # history
                    ws_users.update_cells(cell_list)
                    fetch_data.clear()
                    st.toast("リセット完了")

        # 問題作成（ここを改良！）
        with tab_m:
            st.write("###### どのコンテストの問題を作りますか？")
            # プルダウンでIDを選択
            make_cid_select = st.selectbox("コンテストID", options=["(新規作成)"] + existing_cids, index=1 if len(existing_cids)>0 else 0)
            
            if make_cid_select == "(新規作成)":
                final_make_cid = st.text_input("新しいコンテストIDを入力 (例: B001)")
            else:
                final_make_cid = make_cid_select

            st.divider()
            
            in_no = st.number_input("問題番号", value=1)
            in_q = st.text_area("問題文 (TeX対応)", height=60, placeholder="例: $x^2 + y^2 = 1$ のとき...")
            in_a = st.text_input("正解")
            in_p = st.number_input("配点", value=100)
            
            if st.button("データベースに追加"):
                if final_make_cid and in_a:
                    ws_prob.append_row([final_make_cid, in_no, in_q, in_a, in_p])
                    fetch_data.clear() # キャッシュ更新
                    st.success(f"追加しました！ (ID: {final_make_cid} - No.{in_no})")
                else:
                    st.error("IDと正解は必須です")
        
        # 生徒登録
        with tab_u:
            new_uid = st.text_input("新規ID")
            new_upass = st.text_input("新規Pass")
            new_uname = st.text_input("氏名")
            if st.button("生徒登録"):
                ws_users.append_row([new_uid, new_upass, new_uname, 0, ""])
                fetch_data.clear()
                st.success(f"登録完了: {new_uname}")

# ==========================================
# 🔐 ログイン処理
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["my_id"] = ""
    st.session_state["my_name"] = ""

if st.session_state["logged_in"]:
    st.sidebar.markdown(f"👤 **{st.session_state['my_name']}** さん")
    if st.sidebar.button("ログアウト"):
        st.session_state["logged_in"] = False
        st.rerun()

if not st.session_state["logged_in"]:
    st.markdown("##### 🔐 生徒ログイン")
    with st.form("login_form"):
        input_id = st.text_input("ユーザーID")
        input_pass = st.text_input("パスワード", type="password")
        submitted = st.form_submit_button("ログイン")
        
        if submitted:
            fresh_users = ws_users.get_all_records()
            user_found = False
            found_name = ""
            for u in fresh_users:
                if str(u.get('user_id')) == str(input_id) and str(u.get('password')) == str(input_pass):
                    st.session_state["logged_in"] = True
                    st.session_state["my_id"] = str(input_id)
                    found_name = u.get('name') or str(input_id)
                    st.session_state["my_name"] = found_name
                    user_found = True
                    break
            
            if user_found:
                st.success(f"ようこそ、{found_name} さん！")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("IDまたはパスワードが違います")
    st.stop()

# ==========================================
# 🎮 メイン画面
# ==========================================
my_id = st.session_state["my_id"]
my_name = st.session_state["my_name"]
df_users = pd.DataFrame(users_list)
df_prob = pd.DataFrame(prob_list) # フェッチ済みのデータを使用

my_score = 0
my_solved = []

if not df_users.empty and 'user_id' in df_users.columns:
    df_users['user_id'] = df_users['user_id'].astype(str)
    my_row = df_users[df_users['user_id'] == my_id]
    
    if not my_row.empty:
        raw_score = my_row.iloc[0]['score']
        try: my_score = int(raw_score)
        except: my_score = 0
        
        raw_hist = my_row.iloc[0]['history']
        if pd.isna(raw_hist) or raw_hist == "": my_solved = []
        else: my_solved = str(raw_hist).split(',')
    else:
        st.error("データエラー")
        st.stop()

# タイマー
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

# 問題フィルタリング
if not df_prob.empty and 'contest_id' in df_prob.columns:
    df_prob['contest_id'] = df_prob['contest_id'].astype(str)
    current_problems = df_prob[df_prob['contest_id'] == active_cid].sort_values('id')
else:
    current_problems = pd.DataFrame()

# 正解者数
solver_counts = {}
if 'history' in df_users.columns:
    for h in df_users['history']:
        if pd.isna(h) or h == "": continue
        for i in str(h).split(','): 
            if i: solver_counts[i] = solver_counts.get(i, 0) + 1

@st.fragment(run_every=5)
def show_ranking():
    st.write("### 🏆 Standings")
    u, _, _ = fetch_data() # 最新データを再取得
    df = pd.DataFrame(u)
    if not df.empty:
        df['score'] = pd.to_numeric(df['score'], errors='coerce').fillna(0)
        if 'name' in df.columns:
            df['display_name'] = df['name'].where(df['name'] != "", df['user_id'])
        else:
            df['display_name'] = df['user_id']
        view = df[['display_name', 'score']].sort_values('score', ascending=False).reset_index(drop=True)
        view.columns = ['Name', 'Score']
        view.index += 1
        st.dataframe(view, use_container_width=True)

if status == "開催中":
    st.info(f"🔥 {active_cid} 開催中 | {remaining_msg}")
elif status == "待機中":
    st.info("⏳ 待機中...")
    show_ranking()

if status == "開催中":
    if is_time_up: st.error("⏰ 終了")
    
    col_main, col_rank = st.columns([2, 1])
    
    with col_main:
        st.metric(f"{my_name} さんのスコア", my_score)
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
                                    try:
                                        cell = ws_users.find(my_id)
                                        try: cur_s = int(ws_users.cell(cell.row, 4).value)
                                        except: cur_s = 0
                                        cur_h = ws_users.cell(cell.row, 5).value
                                        new_h = (cur_h + "," + uid) if cur_h else uid
                                        
                                        ws_users.update_cell(cell.row, 4, cur_s + row['pt'])
                                        ws_users.update_cell(cell.row, 5, new_h)
                                        
                                        fetch_data.clear()
                                        st.toast("正解！")
                                        time.sleep(0.5)
                                        st.rerun()
                                    except: st.error("通信エラー")
                                else:
                                    st.error("不正解")
                                    st.session_state["wa_lock"][uid] = time.time() + 10
                                    st.rerun()
    with col_rank:
        show_ranking()

elif status == "終了":
    st.warning("終了しました")
    show_ranking()
