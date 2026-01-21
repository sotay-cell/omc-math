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

# 日本時間の定義
JST = pytz.timezone('Asia/Tokyo')

# --- 1. データベース接続 ---
@st.cache_resource
def get_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    try:
        # パターンA: Streamlit Cloud (Secrets)
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        # パターンB: Colab/ローカル
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name('secrets.json', scope)

        client = gspread.authorize(creds)
        sh = client.open("omc_db")
        
        # シート取得（なければ作成）
        try:
            ws_prob = sh.worksheet("problems")
        except:
            ws_prob = sh.add_worksheet(title="problems", rows="100", cols="20")
            
        return sh.sheet1, ws_prob

    except Exception as e:
        return None, None

# タイトル
st.title("🏆 リアルタイム数学コンテスト DX")

sheet_rank, sheet_prob = get_connection()
if sheet_rank is None:
    st.error("🚨 接続エラー: Secretsの設定を確認してください。")
    st.stop()

# --- 2. 管理パネル (B-4: アプリ内管理) ---
# サイドバーに管理者用ログインを設置
with st.sidebar.expander("👮 管理者メニュー"):
    admin_pass = st.text_input("パスワード", type="password")
    
    # パスワードは仮で "admin123" に設定しています。自由に変えてください。
    if admin_pass == "admin123":
        st.success("認証成功")
        
        # コンテスト設定フォーム
        new_cid = st.text_input("開催するコンテストID", value="A001")
        duration_min = st.number_input("制限時間（分）", min_value=1, value=30)
        
        col_btn1, col_btn2, col_btn3 = st.columns(3)
        
        # 開始ボタン
        if col_btn1.button("▶ 開始"):
            now = datetime.datetime.now(JST)
            end_time = now + datetime.timedelta(minutes=duration_min)
            end_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
            
            # シートに書き込み（D1=状態, E1=ID, F1=終了時刻）
            sheet_rank.update_acell('D1', '開催中')
            sheet_rank.update_acell('E1', new_cid)
            sheet_rank.update_acell('F1', end_str)
            st.toast("コンテストを開始しました！")
            time.sleep(1)
            st.rerun()
            
        # 終了ボタン
        if col_btn2.button("⏹ 終了"):
            sheet_rank.update_acell('D1', '終了')
            st.toast("コンテストを終了しました。")
            time.sleep(1)
            st.rerun()

        # リセットボタン（要注意）
        if col_btn3.button("🗑 リセット"):
            # 1行目（ヘッダー）を残して全削除
            all_rows = sheet_rank.get_all_values()
            if len(all_rows) > 1:
                sheet_rank.batch_clear([f"A2:D{len(all_rows)}"])
            st.toast("ランキングをリセットしました。")

# --- 3. 設定とデータの読み込み ---
try:
    # ステータス等の読み込み
    vals = sheet_rank.get('D1:F1') # D1, E1, F1を一括取得
    if vals:
        row_val = vals[0]
        status = row_val[0] if len(row_val) > 0 else "待機中"
        active_cid = str(row_val[1]) if len(row_val) > 1 else "1"
        end_time_str = row_val[2] if len(row_val) > 2 else ""
    else:
        status, active_cid, end_time_str = "待機中", "1", ""

except:
    status, active_cid, end_time_str = "待機中", "1", ""

# タイマー計算 (A-1: 残り時間)
remaining_msg = ""
is_time_up = False

if status == "開催中" and end_time_str:
    try:
        end_dt = datetime.datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S')
        end_dt = JST.localize(end_dt) # 日本時間として扱う
        now = datetime.datetime.now(JST)
        diff = end_dt - now
        
        if diff.total_seconds() > 0:
            # 残り時間を表示
            mm, ss = divmod(int(diff.total_seconds()), 60)
            remaining_msg = f"⏱ 残り時間: {mm}分 {ss}秒"
        else:
            remaining_msg = "⏱ タイムアップ！"
            is_time_up = True
            # 自動終了機能（オプション）
            # status = "終了" 
    except:
        remaining_msg = ""

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

# --- 4. ユーザー処理 ---
if "wa_lock" not in st.session_state:
    st.session_state["wa_lock"] = {} # WAロック管理用

user_name = st.sidebar.text_input("参加者名", key="login")
if not user_name:
    st.warning("👈 名前を入力してください")
    # 管理者以外はここで止める
    if not admin_pass: 
        st.stop()

# 全データ取得（ランキング＆正解者数集計用）
data_rank = sheet_rank.get_all_records()
df_rank = pd.DataFrame(data_rank)

# 自分のデータ取得
score = 0
solved = []
if not df_rank.empty and user_name in df_rank['user'].values:
    row = df_rank[df_rank['user'] == user_name].iloc[0]
    score = int(row['score'])
    solved = str(row['solved_history']).split(',') if str(row['solved_history']) else []
else:
    # 名前入力済みかつ開催中なら登録
    if user_name and status != "待機中":
        sheet_rank.append_row([user_name, 0, "", ""])
        st.toast(f"Welcome {user_name}!")

# 正解者数の集計 (A-3: Real-time Solver Count)
solver_counts = {}
if not df_rank.empty:
    for history in df_rank['solved_history']:
        if history:
            ids = str(history).split(',')
            for i in ids:
                solver_counts[i] = solver_counts.get(i, 0) + 1

# --- 5. 画面表示 ---

# ヘッダー情報（残り時間など）
if status == "開催中":
    # タイムアップ時は強制終了モード
    if is_time_up:
        st.error("⏰ 制限時間が終了しました！ 回答は締め切られました。")
    else:
        st.info(f"🔥 コンテスト開催中 | {remaining_msg}")

if status == "待機中":
    st.info(f"⏳ 第{active_cid}回コンテスト: 準備中...")
    if st.button("🔄 最新状態に更新"): st.rerun()

elif status == "開催中":
    c1, c2 = st.columns([3, 1])
    c1.metric(f"現在のスコア (Round {active_cid})", score)
    if c2.button("🔄 更新"): st.rerun()
    
    col_q, col_r = st.columns([2, 1])
    
    # --- 問題表示エリア ---
    with col_q:
        if current_problems.empty:
            st.warning("問題がありません")
        
        for i, row in current_problems.iterrows():
            pid = str(row['id'])
            uid = f"{active_cid}_{pid}"
            
            # 正解者数表示 (A-3)
            solvers = solver_counts.get(uid, 0)
            
            # カードヘッダー作成
            card_title = f"Q{pid} ({row['pt']}点) - 正解: {solvers}人"
            
            if uid in solved:
                st.success(f"✅ {card_title} [クリア！]")
            else:
                # WAロックチェック (A-2: Wrong Answer Penalty)
                lock_time = st.session_state["wa_lock"].get(uid, 0)
                remaining_lock = lock_time - time.time()
                
                with st.expander(card_title):
                    st.latex(row['q'])
                    
                    if is_time_up:
                        st.write("🚫 終了しました")
                    elif remaining_lock > 0:
                        st.error(f"❌ WAペナルティ: あと {int(remaining_lock)}秒 待ってください")
                    else:
                        ans = st.text_input("回答", key=f"in_{uid}")
                        if st.button("送信", key=f"btn_{uid}"):
                            # 正誤判定
                            if str(ans).strip() == str(row['ans']):
                                st.balloons()
                                # シート更新
                                try:
                                    cell = sheet_rank.find(user_name)
                                    # データ再取得して競合防ぐ
                                    curr_score = int(sheet_rank.cell(cell.row, 2).value)
                                    curr_hist = sheet_rank.cell(cell.row, 3).value
                                    new_hist = (curr_hist + "," + uid) if curr_hist else uid
                                    
                                    sheet_rank.update_cell(cell.row, 2, curr_score + row['pt'])
                                    sheet_rank.update_cell(cell.row, 3, new_hist)
                                    st.toast("正解！ナイス！")
                                    time.sleep(1)
                                    st.rerun()
                                except:
                                    st.error("通信エラー。もう一度押してください。")
                            else:
                                st.error("不正解... (10秒ロックされます)")
                                # ペナルティ設定: 現在時刻 + 10秒
                                st.session_state["wa_lock"][uid] = time.time() + 10
                                st.rerun()

    # --- 順位表エリア ---
    with col_r:
        st.write("### 🏆 順位表")
        if not df_rank.empty:
            # スコア順にソート
            view_df = df_rank[['user', 'score']].sort_values('score', ascending=False).reset_index(drop=True)
            view_df.index += 1
            st.dataframe(view_df, use_container_width=True)

elif status == "終了":
    st.warning("🏁 コンテストは終了しました")
    st.balloons()
    if not df_rank.empty:
        view_df = df_rank[['user', 'score']].sort_values('score', ascending=False).reset_index(drop=True)
        view_df.index += 1
        st.dataframe(view_df)
