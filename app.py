import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import json
import datetime
import pytz

# --- ページ設定 ---
st.set_page_config(page_title="Math Contest DX", layout="wide")
JST = pytz.timezone('Asia/Tokyo')

# --- 1. データベース接続とキャッシュ設定 ---

@st.cache_resource
def get_connection():
    """スプレッドシートへの接続を確立する（リソースキャッシュ）"""
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
    except Exception as e: return None, None

@st.cache_data(ttl=5)
def fetch_ranking_data():
    """ランキングデータを取得し、5秒間キャッシュする（API制限対策）"""
    sheet_rank, _ = get_connection()
    if sheet_rank:
        return sheet_rank.get_all_records()
    return []

# 接続チェック
sheet_rank, sheet_prob = get_connection()
if sheet_rank is None:
    st.error("🚨 接続エラー: Secretsの設定を確認してください。")
    st.stop()

st.title("🏆 リアルタイム数学コンテスト DX")

# --- 2. 管理パネル ---
with st.sidebar.expander("👮 管理者メニュー"):
    admin_pass = st.text_input("パスワード", type="password")
    if admin_pass == "admin123":
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
            st.write("###### 新しい問題を追加")
            in_cid = st.text_input("ID", value=new_cid)
            in_no = st.number_input("No.", min_value=1, value=1)
            in_pt = st.number_input("Pt", step=100, value=100)
            in_ans = st.text_input("正解")
            in_q = st.text_area("問題文 (LaTeX: $...$)", height=100)
            st.caption("プレビュー:")
            if in_q: st.markdown(in_q)
            if st.button("追加"):
                sheet_prob.append_row([in_cid, in_no, in_q, in_ans, in_pt])
                st.success(f"追加: {in_cid}-{in_no}")

# --- 3. データ読み込み（メイン） ---
try:
    vals = sheet_rank.get('D1:F1')
    status = vals[0][0] if vals and len(vals[0])>0 else "待機中"
    active_cid = str(vals[0][1]) if vals and len(vals[0])>1 else "1"
    end_time_str = vals[0][2] if vals and len(vals[0])>2 else ""
except:
    status, active_cid, end_time_str = "待機中", "1", ""

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

# 問題取得
try:
    prob_data = sheet_prob.get_all_records()
    df_prob = pd.DataFrame(prob_data)
    if not df_prob.empty and 'contest_id' in df_prob.columns:
        df_prob['contest_id'] = df_prob['contest_id'].astype(str)
        current_problems = df_prob[df_prob['contest_id'] == active_cid].sort_values('id')
    else: current_problems = pd.DataFrame()
except: current_problems = pd.DataFrame()

# --- 4. ユーザー処理 ---
if "wa_lock" not in st.session_state: st.session_state["wa_lock"] = {}
user_name = st.sidebar.text_input("参加者名", key="login")
if not user_name:
    if not admin_pass: st.stop()

# 自分のスコア計算用（リアルタイム更新はしない部分）
raw_rank_data = fetch_ranking_data() # キャッシュから取得
df_rank = pd.DataFrame(raw_rank_data)
score, solved = 0, []

if not df_rank.empty and user_name in df_rank['user'].values:
    row = df_rank[df_rank['user'] == user_name].iloc[0]
    score = int(row['score'])
    solved = str(row['solved_history']).split(',') if str(row['solved_history']) else []
else:
    if user_name and status != "待機中":
        # 新規ユーザー登録は直接シートへ（キャッシュ破棄のため）
        sheet_rank.append_row([user_name, 0, "", ""])
        fetch_ranking_data.clear() # キャッシュクリア
        st.toast(f"Welcome {user_name}!")
        st.rerun()

# 正解者数集計
solver_counts = {}
if not df_rank.empty:
    for h in df_rank['solved_history']:
        for i in str(h).split(','): 
            if i: solver_counts[i] = solver_counts.get(i, 0) + 1

# --- 5. 自動更新する順位表パーツ ---
@st.fragment(run_every=5) # 5秒ごとにここだけ再実行！
def auto_ranking_table():
    st.write("### 🏆 順位表 (LIVE)")
    # キャッシュされた最新データを取得
    live_data = fetch_ranking_data()
    df_live = pd.DataFrame(live_data)
    
    if not df_live.empty:
        # スコア順ソート
        view_df = df_live[['user', 'score']].sort_values('score', ascending=False).reset_index(drop=True)
        view_df.index += 1
        st.dataframe(view_df, use_container_width=True)
    else:
        st.write("データなし")

# --- 6. メイン画面表示 ---
if status == "開催中":
    if is_time_up: st.error("⏰ 終了！")
    else: st.info(f"🔥 開催中 | {remaining_msg}")

if status == "待機中":
    st.info(f"⏳ 第{active_cid}回: 準備中...")
    # 待機中も順位表だけは見せる
    auto_ranking_table()

elif status == "開催中":
    c1, c2 = st.columns([3, 1])
    c1.metric(f"Score", score)
    if c2.button("手動更新"): st.rerun()
    
    col_q, col_r = st.columns([2, 1])
    
    # 問題エリア（ここは入力中かもしれないので自動更新しない）
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
                                    fetch_ranking_data.clear() # 即座に反映させるためキャッシュ消去
                                    st.rerun()
                                except: st.error("通信エラー")
                            else:
                                st.error("不正解...")
                                st.session_state["wa_lock"][uid] = time.time() + 10
                                st.rerun()

    # 順位表エリア（ここに自動更新パーツを配置）
    with col_r:
        auto_ranking_table()

elif status == "終了":
    st.warning("終了")
    auto_ranking_table()
