import streamlit as st
import pandas as pd
import os
import random
import re
from datetime import datetime
import time
import hashlib
import math
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --------------------------------------------------------
# 1. 라이브러리 로드 및 에러 처리
# --------------------------------------------------------
try:
    from streamlit_calendar import calendar
except ImportError:
    st.error("🚨 'streamlit-calendar' 라이브러리가 필요합니다.")
    st.stop()

try:
    import pdfplumber
except ImportError:
    pass 

# ==========================================
# 2. 구글 스프레드시트 연결 설정 (핵심!)
# ==========================================
# 구글 시트 이름 (구글 드라이브에 이 이름으로 파일을 만들어두세요)
SHEET_NAME = "ontop_db" 

# 이미지 저장을 위한 로컬 폴더 (이미지는 시트에 저장 불가하므로 임시 저장됨)
IMAGE_DIR = "problem_images"
if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

# --- 구글 시트 인증 및 연결 함수 (캐싱 사용) ---
@st.cache_resource
def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # secrets.toml에서 인증 정보 가져오기
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    client = gspread.authorize(creds)
    return client

# --- 데이터 로드 함수 (구글 시트) ---
def load_data(worksheet_name, columns):
    """구글 시트의 특정 탭(worksheet_name)에서 데이터를 가져옵니다."""
    try:
        client = init_connection()
        sheet = client.open(SHEET_NAME)
        try:
            worksheet = sheet.worksheet(worksheet_name)
            data = worksheet.get_all_records()
            df = pd.DataFrame(data)
            
            # 모든 데이터를 문자열로 변환 (에러 방지)
            df = df.astype(str)
            
            # 필수 컬럼이 없으면 추가 (빈 데이터프레임일 경우 대비)
            for col in columns:
                if col not in df.columns:
                    df[col] = ""
            return df
        except gspread.WorksheetNotFound:
            # 탭이 없으면 새로 생성하고 헤더 추가
            worksheet = sheet.add_worksheet(title=worksheet_name, rows=100, cols=20)
            worksheet.append_row(columns) # 헤더 추가
            return pd.DataFrame(columns=columns)
    except Exception as e:
        # 연결 오류 시 빈 데이터프레임 반환 (앱이 죽지 않도록)
        return pd.DataFrame(columns=columns)

# --- 데이터 저장 함수 (구글 시트) ---
def save_data(worksheet_name, new_df):
    """데이터프레임을 구글 시트의 특정 탭에 덮어씁니다."""
    try:
        client = init_connection()
        sheet = client.open(SHEET_NAME)
        try:
            worksheet = sheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            worksheet = sheet.add_worksheet(title=worksheet_name, rows=100, cols=20)
        
        # 데이터프레임 내용을 리스트로 변환 (헤더 포함)
        params = [new_df.columns.values.tolist()] + new_df.values.tolist()
        
        # 시트 클리어 후 업데이트
        worksheet.clear()
        worksheet.update(params)
    except Exception as e:
        st.error(f"저장 중 오류 발생: {e}")

# --- 유틸리티 함수들 ---
def make_hashes(password):
    return hashlib.sha256(str.encode(str(password))).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

def get_yt_start_time(url):
    if not isinstance(url, str): return 0
    match = re.search(r'[?&](t|start)=(\d+)', url)
    return int(match.group(2)) if match else 0

# --- 초기 계정 세팅 (DB 확인 후 없으면 생성) ---
# users 탭 확인 (파일명 대신 탭 이름 'users' 사용)
df_check = load_data('users', ['id'])
if df_check.empty:
    default_users = pd.DataFrame([
        {'id': 'admin', 'pw': make_hashes('admin123'), 'name': '원장님', 'role': 'teacher', 'subject': '전체', 'linked_student': '', 'math_class': '', 'eng_class': ''},
        {'id': 't_eng', 'pw': make_hashes('1234'), 'name': '최영석', 'role': 'teacher', 'subject': '영어', 'linked_student': '', 'math_class': '', 'eng_class': ''},
        {'id': 't_math', 'pw': make_hashes('1234'), 'name': '어혜원', 'role': 'teacher', 'subject': '수학', 'linked_student': '', 'math_class': '', 'eng_class': ''},
        {'id': 'student1', 'pw': make_hashes('1234'), 'name': '김철수', 'role': 'student', 'subject': '', 'linked_student': '', 'math_class': '수학A', 'eng_class': '영어B'},
        {'id': 'parent1', 'pw': make_hashes('1234'), 'name': '철수부모님', 'role': 'parent', 'subject': '', 'linked_student': 'student1', 'math_class': '', 'eng_class': ''}
    ])
    save_data('users', default_users)


# ==========================================
# 3. UI 스타일 및 세션 초기화
# ==========================================
st.set_page_config(page_title="온탑영어펀한수학학원", layout="wide", page_icon="🎓")

# 세션 초기화
if 'logged_in' not in st.session_state: st.session_state.update({'logged_in': False, 'user_id': None, 'user_role': None, 'user_name': None, 'user_subject': "", 'linked_student': ""})
if 'cal_view_date' not in st.session_state: st.session_state['cal_view_date'] = None
if 'last_result' not in st.session_state: st.session_state['last_result'] = None 
if 'current_options' not in st.session_state: st.session_state['current_options'] = None

# 모바일 최적화 CSS
st.markdown("""
    <style>
    .stApp { background-color: #F8F9FA; }
    .main-title { font-size: 2.0rem; font-weight: 800; color: #1E3A8A; text-align: center; margin-bottom: 20px; }
    
    /* 플래시카드 */
    .flashcard {
        background-color: white; padding: 40px 20px; border-radius: 20px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.1); text-align: center;
        margin-bottom: 30px; border: 2px solid #E5E7EB; min-height: 200px;
        display: flex; flex-direction: column; justify-content: center; align-items: center;
        transition: all 0.3s ease;
    }
    .flashcard.correct { border: 3px solid #4CAF50 !important; background-color: #E8F5E9 !important; transform: scale(1.02); }
    .flashcard.wrong { border: 3px solid #F44336 !important; background-color: #FFEBEE !important; animation: shake 0.5s; }
    
    .word-text { font-size: 2.5rem; font-weight: 800; color: #1F2937; margin-bottom: 10px; }
    .meaning-text { font-size: 1.8rem; color: #2563EB; font-weight: 600; margin-top: 15px; }
    .book-badge { background-color: #DBEAFE; color: #1E40AF; padding: 5px 10px; border-radius: 15px; font-size: 0.8rem; margin-bottom: 10px; display: inline-block; }
    
    /* 버튼 */
    div.stButton > button { width: 100%; border-radius: 8px; font-weight: bold; height: 45px; }
    
    @keyframes shake {
        0% { transform: translate(1px, 1px) rotate(0deg); } 20% { transform: translate(-3px, 0px) rotate(1deg); } 40% { transform: translate(1px, -1px) rotate(1deg); } 60% { transform: translate(-3px, 1px) rotate(0deg); } 80% { transform: translate(-1px, -1px) rotate(1deg); } 100% { transform: translate(1px, -2px) rotate(-1deg); }
    }
    
    /* 모바일 달력 및 UI 최적화 */
    @media only screen and (max-width: 640px) {
        div[data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: nowrap !important; gap: 1px !important; }
        div[data-testid="column"] { min-width: 0px !important; flex: 1 1 auto !important; width: auto !important; padding: 0px !important; }
        div.stButton > button { height: 35px !important; min-height: 35px !important; padding: 0px !important; font-size: 11px !important; margin: 0px !important; border-radius: 3px !important; white-space: normal !important; line-height: 1.2 !important; }
        div[data-baseweb="select"] > div { font-size: 13px !important; min-height: 35px !important; }
        .day-header { font-size: 10px !important; text-align: center !important; margin-bottom: 2px !important; white-space: nowrap; }
        .main-title { font-size: 1.6rem; }
        .word-text { font-size: 1.8rem; }
        .meaning-text { font-size: 1.4rem; }
        .block-container { padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 4. [기능] 단어 암기 프로그램
# ==========================================
def start_flashcard_session(word_list, user_id, mode, test_info=""):
    random.shuffle(word_list)
    st.session_state.update({
        'vocab_session': True, 'study_list': word_list, 'current_word_idx': 0,
        'show_meaning': False, 'session_mode': mode, 'session_user': user_id,
        'test_score': 0, 'test_info': test_info, 'last_result': None, 
        'show_answer_sub': False, 'current_options': None
    })
    st.rerun()

def render_flashcard_session():
    if not st.session_state.get('vocab_session'): return
    
    st.divider()
    idx = st.session_state['current_word_idx']
    study_list = st.session_state['study_list']
    total = len(study_list)
    mode = st.session_state['session_mode']
    user_id = st.session_state['session_user']
    
    if idx >= total:
        if 'test' in mode:
            score = st.session_state['test_score']
            st.balloons()
            st.success(f"## 🏁 테스트 종료! 점수: {score} / {total}")
            if st.button("결과 저장 및 종료", type="primary", key="btn_save_test", use_container_width=True):
                # 탭: vocab_test_log
                df_test = load_data('vocab_test_log', ['student_id', 'date', 'info', 'score'])
                new_log = pd.DataFrame([{
                    'student_id': user_id,
                    'date': datetime.now().strftime("%Y-%m-%d %H:%M"),
                    'info': st.session_state['test_info'],
                    'score': f"{score}/{total}"
                }])
                save_data('vocab_test_log', pd.concat([df_test, new_log], ignore_index=True))
                st.session_state['vocab_session'] = False
                st.session_state['last_result'] = None
                st.rerun()
        else:
            st.success("✅ 학습이 완료되었습니다!")
            if st.button("종료", key="btn_end_learn", use_container_width=True):
                st.session_state['vocab_session'] = False
                st.session_state['last_result'] = None
                st.rerun()
        return

    current_word = study_list[idx]
    word_text = current_word['word']
    meaning_text = current_word['meaning']
    book_text = current_word.get('book', '')

    mode_text = "실전 테스트" if 'test' in mode else "학습"
    st.markdown(f"#### 🧠 {mode_text} 중 ({idx+1}/{total})")

    card_class = "flashcard"
    if st.session_state['last_result'] == 'correct': card_class += " correct"
    elif st.session_state['last_result'] == 'wrong': card_class += " wrong"

    # [모드 1] 객관식
    if mode == 'test_objective':
        st.markdown(f"""
            <div class="{card_class}">
                <div class="book-badge">{book_text}</div>
                <div class="word-text">{word_text}</div>
            </div>
        """, unsafe_allow_html=True)
        
        if st.session_state['current_options'] is None:
            # 탭: vocab
            df_vocab = load_data('vocab', ['book', 'word', 'meaning'])
            same_book_words = df_vocab[df_vocab['book'] == book_text]['meaning'].tolist()
            if len(same_book_words) < 4: same_book_words = df_vocab['meaning'].tolist()
            
            distractors = list(set([m for m in same_book_words if m != meaning_text]))
            if len(distractors) >= 3: options = random.sample(distractors, 3) + [meaning_text]
            else: options = distractors + [meaning_text]
            random.shuffle(options)
            st.session_state['current_options'] = options
            
        options = st.session_state['current_options']
        
        for i, opt in enumerate(options):
            if st.button(opt, key=f"opt_{idx}_{i}", use_container_width=True):
                if opt == meaning_text:
                    st.toast("정답입니다! 🎉", icon="✅")
                    st.session_state['last_result'] = 'correct'
                    update_vocab_progress(user_id, current_word, is_correct=True, mode=mode)
                    st.session_state['current_word_idx'] += 1
                    st.session_state['current_options'] = None
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.session_state['last_result'] = 'wrong'
                    st.toast(f"틀렸습니다. 정답: {meaning_text}", icon="❌")
                    update_vocab_progress(user_id, current_word, is_correct=False, mode=mode)
                    st.session_state['current_word_idx'] += 1
                    st.session_state['current_options'] = None
                    time.sleep(1.0)
                    st.rerun()

    # [모드 2] 주관식 (비밀번호 타입)
    elif mode == 'subjective' or mode == 'test_subjective':
        st.markdown(f"""
            <div class="{card_class}">
                <div class="book-badge">{book_text}</div>
                <div class="meaning-text" style="color:#333;">{meaning_text}</div>
                <div style="color:#999; margin-top:20px;">영어 단어를 입력하세요</div>
            </div>
        """, unsafe_allow_html=True)
        
        if not st.session_state['show_answer_sub']:
            with st.form(key=f"sub_form_{idx}"):
                user_input = st.text_input("정답 입력", key=f"input_{idx}", type="password").strip()
                sub_btn = st.form_submit_button("제출", type="primary", use_container_width=True)
                giveup_btn = st.form_submit_button("모르겠어요 (정답)", use_container_width=True)
            
            if sub_btn:
                if user_input.lower() == word_text.lower():
                    st.session_state['last_result'] = 'correct'
                    update_vocab_progress(user_id, current_word, is_correct=True, mode=mode)
                    st.session_state['current_word_idx'] += 1
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.session_state['last_result'] = 'wrong'
                    st.error("틀렸습니다. 다시 시도해보세요.")
            
            if giveup_btn:
                st.session_state['last_result'] = 'wrong'
                st.session_state['show_answer_sub'] = True
                st.rerun()
        else:
            st.error(f"정답: {word_text}")
            st.warning("스펠링을 따라 쓰고 넘어가세요.")
            with st.form(key=f"copy_form_{idx}"):
                copy_input = st.text_input("따라 쓰기", key=f"copy_{idx}")
                next_btn = st.form_submit_button("다음 문제", type="primary", use_container_width=True)
            if next_btn:
                update_vocab_progress(user_id, current_word, is_correct=False, mode=mode)
                st.session_state['show_answer_sub'] = False
                st.session_state['last_result'] = None
                st.session_state['current_word_idx'] += 1
                st.rerun()

    # [모드 3] 플래시카드
    else:
        st.markdown(f"""
            <div class="{card_class}">
                <div class="book-badge">{book_text}</div>
                <div class="word-text">{word_text}</div>
                {'<div class="meaning-text">' + meaning_text + '</div>' if st.session_state['show_meaning'] else '<div style="color:#999; margin-top:20px;">(터치하여 뜻 확인)</div>'}
            </div>
        """, unsafe_allow_html=True)

        if not st.session_state['show_meaning']:
            if st.button("뜻 확인하기 👁️", use_container_width=True, key=f"rev_{idx}"):
                st.session_state['show_meaning'] = True
                st.rerun()
        else:
            c1, c2 = st.columns(2)
            if c1.button("⭕ 알아요", type="primary", use_container_width=True, key=f"ok_{idx}"):
                st.session_state['last_result'] = 'correct'
                update_vocab_progress(user_id, current_word, is_correct=True, mode=mode)
                st.session_state['current_word_idx'] += 1
                st.session_state['show_meaning'] = False
                time.sleep(0.3)
                st.rerun()
            if c2.button("❌ 몰라요", use_container_width=True, key=f"no_{idx}"):
                st.session_state['last_result'] = 'wrong'
                update_vocab_progress(user_id, current_word, is_correct=False, mode=mode)
                st.session_state['current_word_idx'] += 1
                st.session_state['show_meaning'] = False
                time.sleep(0.3)
                st.rerun()
    st.progress((idx)/total)

def update_vocab_progress(user_id, word_data, is_correct, mode):
    if 'test' in mode:
        if is_correct: 
            st.session_state['test_score'] += 1
            return 
        else:
            # 탭: vocab_test_wrongs
            df_t_wrong = load_data('vocab_test_wrongs', ['student_id', 'book', 'word', 'date'])
            if not ((df_t_wrong['student_id'] == user_id) & (df_t_wrong['word'] == word_data['word'])).any():
                new_w = pd.DataFrame([{
                    'student_id': user_id, 'book': word_data.get('book',''), 
                    'word': word_data['word'], 'date': datetime.now().strftime("%Y-%m-%d")
                }])
                save_data('vocab_test_wrongs', pd.concat([df_t_wrong, new_w], ignore_index=True))
            return

    # 탭: vocab_prog
    df_prog = load_data('vocab_prog', ['student_id', 'book', 'word', 'streak', 'status'])
    mask = (df_prog['student_id'] == user_id) & (df_prog['book'] == word_data.get('book','')) & (df_prog['word'] == word_data['word'])
    current = df_prog[mask]
    
    streak = int(float(current.iloc[0]['streak'])) if not current.empty else 0
    current_status = current.iloc[0]['status'] if not current.empty else 'learning'
    master_threshold = 2 if mode == 'subjective' or current_status == 'learning' else 4

    if is_correct:
        streak += 1
        status = 'mastered' if streak >= master_threshold else 'learning'
        if status == 'mastered' and 'test' not in mode: st.toast("👑 마스터 완료!", icon="🎉")
    else:
        streak = 0
        status = 'learning'
        if 'test' not in mode: st.toast("오답노트 저장", icon="🔥")

    df_prog = df_prog[~mask]
    new_row = pd.DataFrame([{
        'student_id': user_id, 'book': word_data.get('book',''), 'word': word_data['word'], 
        'streak': streak, 'status': status
    }])
    save_data('vocab_prog', pd.concat([df_prog, new_row], ignore_index=True))

def vocab_study_session(user_id):
    st.subheader("🧠 단어 마스터 프로그램")
    # 탭: vocab, vocab_prog
    df_vocab = load_data('vocab', ['book', 'day', 'word', 'meaning'])
    df_prog = load_data('vocab_prog', ['student_id', 'book', 'word', 'streak', 'status'])
    if df_vocab.empty: st.info("등록된 단어장이 없습니다."); return

    t1, t2, t3, t4, t5 = st.tabs(["📖 챕터별 학습", "❌ 오답 목록", "🏆 마스터 목록", "📝 누적 테스트", "📒 누적 오답"])

    with t1:
        books = sorted(df_vocab['book'].unique())
        c1, c2 = st.columns(2)
        s_book = c1.selectbox("책", books, key="vb")
        b_vocab = df_vocab[df_vocab['book'] == s_book]
        days = sorted(b_vocab['day'].unique(), key=natural_sort_key)
        s_day = c2.selectbox("Day", days, key="vd")
        
        target = b_vocab[b_vocab['day'] == s_day]
        st.caption(f"총 {len(target)} 단어")
        
        mode_radio = st.radio("학습 방식", ["플래시카드 (보고 외우기)", "주관식 (스펠링 쓰기)"], horizontal=True, key="chap_mode")
        mode_code = 'subjective' if "주관식" in mode_radio else 'learning'

        c_a, c_w = st.columns(2)
        if c_a.button("🚀 전체 학습", key="btn_learn_all", use_container_width=True):
            study_list = []
            for _, r in target.iterrows():
                p = df_prog[(df_prog['student_id']==user_id) & (df_prog['word']==r['word'])]
                if not (not p.empty and p.iloc[0]['status'] == 'mastered'):
                    study_list.append(r.to_dict())
            start_flashcard_session(study_list, user_id, mode_code)
            
        if c_w.button("❌ 오답만", key="btn_learn_wrong_chap", use_container_width=True):
            study_list = []
            for _, r in target.iterrows():
                p = df_prog[(df_prog['student_id']==user_id) & (df_prog['word']==r['word'])]
                if not p.empty and p.iloc[0]['status'] == 'learning':
                    study_list.append(r.to_dict())
            if study_list: start_flashcard_session(study_list, user_id, mode_code)
            else: st.info("오답 없음")

    with t2:
        wrongs = df_prog[(df_prog['student_id']==user_id) & (df_prog['status']=='learning')]
        if wrongs.empty: st.info("오답이 없습니다.")
        else:
            w_details = pd.merge(wrongs, df_vocab, on=['book', 'word'], how='left')[['book', 'day', 'word', 'meaning', 'streak']]
            st.dataframe(w_details, use_container_width=True)
            c_o1, c_o2 = st.columns(2)
            if c_o1.button("🔥 플래시카드 재학습", key="btn_wr_flash", use_container_width=True): 
                start_flashcard_session(w_details.to_dict('records'), user_id, "learning")
            if c_o2.button("✍️ 주관식 재학습", key="btn_wr_sub", use_container_width=True): 
                start_flashcard_session(w_details.to_dict('records'), user_id, "subjective")

    with t3:
        masters = df_prog[(df_prog['student_id']==user_id) & (df_prog['status']=='mastered')]
        if masters.empty: st.info("마스터한 단어가 없습니다.")
        else:
            m_details = pd.merge(masters, df_vocab, on=['book', 'word'], how='left')[['book', 'day', 'word', 'meaning']]
            st.dataframe(m_details, use_container_width=True)
            if st.button("♻️ 마스터 단어 복습", key="btn_review_master", use_container_width=True): 
                start_flashcard_session(m_details.to_dict('records'), user_id, "review")

    with t4:
        st.write("##### 누적 실전 모의고사")
        t_book = st.selectbox("책 선택", sorted(df_vocab['book'].unique()), key="tb")
        t_v = df_vocab[df_vocab['book']==t_book]
        t_days = sorted(t_v['day'].unique(), key=natural_sort_key)
        
        s_d = st.selectbox("시작 Day", t_days, key="tsd")
        e_d = st.selectbox("종료 Day", t_days, index=len(t_days)-1, key="ted")
        
        test_type = st.radio("테스트 방식", ["객관식(4지 선다)", "주관식(스펠링)"], horizontal=True, key="test_type")
        t_mode = "test_objective" if "객관식" in test_type else "test_subjective" 

        try:
            si, ei = t_days.index(s_d), t_days.index(e_d)
            days_rng = t_days[si:ei+1] if si <= ei else []
        except: days_rng = []
        
        pool = t_v[t_v['day'].isin(days_rng)]
        st.write(f"대상 단어: {len(pool)}개")
        q_cnt = st.number_input("문제 수", 5, len(pool) if len(pool)>5 else 5, min(20, len(pool)) if len(pool)>20 else 5, key="test_q_cnt")
        
        if st.button("🏁 테스트 시작", key="btn_start_test", use_container_width=True):
            if pool.empty: st.error("단어가 없습니다.")
            else:
                test_set = pool.sample(n=q_cnt).to_dict('records')
                test_desc = f"{t_book} ({s_d}~{e_d}) [{'객관식' if 'objective' in t_mode else '주관식'}]"
                start_flashcard_session(test_set, user_id, t_mode, test_desc)
    
    with t5:
        st.write("##### 🚧 누적 테스트 오답 노트")
        # 탭: vocab_test_wrongs
        df_tw = load_data('vocab_test_wrongs', ['student_id', 'book', 'word', 'date'])
        my_tw = df_tw[df_tw['student_id'] == user_id]
        
        if my_tw.empty: st.info("누적 테스트 오답이 없습니다.")
        else:
            tw_details = pd.merge(my_tw, df_vocab, on=['book', 'word'], how='left')[['date', 'book', 'word', 'meaning']]
            st.dataframe(tw_details, use_container_width=True)
            
            c_tr1, c_tr2 = st.columns(2)
            if c_tr1.button("🔥 오답 학습하기", key="btn_study_tw", use_container_width=True):
                start_flashcard_session(tw_details.to_dict('records'), user_id, "learning")
            
            del_w = st.selectbox("삭제할 단어 선택", tw_details['word'], key="sel_del_tw")
            if c_tr2.button("삭제", key="btn_del_tw", use_container_width=True):
                df_tw = df_tw[~((df_tw['student_id']==user_id) & (df_tw['word']==del_w))]
                save_data('vocab_test_wrongs', df_tw)
                st.rerun()

    render_flashcard_session()

# ==========================================
# 5. [기능] 달력 컴포넌트
# ==========================================
def render_calendar(student_id):
    st.markdown("#### 📅 학습 기록 달력")
    # 탭: learning_log
    df_log = load_data('learning_log', ['student_id', 'date', 'content', 'teacher_name', 'subject'])
    my_logs = df_log[df_log['student_id'] == student_id]
    
    events = []
    for _, row in my_logs.iterrows():
        color = "#3B82F6"
        if "수학" in str(row['subject']): color = "#EF4444"
        elif "영어" in str(row['subject']): color = "#10B981"
        events.append({"title": f"[{row['subject']}]", "start": row['date'], "color": color})

    cal = calendar(events=events, options={"headerToolbar": {"left": "prev,next", "center": "title", "right": "today"}, "initialView": "dayGridMonth", "contentHeight": "auto"}, key=f"cal_{student_id}")
    
    st.divider()
    clicked_date = None
    if cal.get("dateClick"): clicked_date = cal["dateClick"].get("dateStr")
    elif cal.get("eventClick"):
        s = cal["eventClick"]["event"]["start"]
        clicked_date = s.split("T")[0] if "T" in s else s

    if clicked_date:
        st.write(f"**📌 {clicked_date} 기록**")
        logs = my_logs[my_logs['date'] == clicked_date]
        if logs.empty: st.info("기록 없음")
        else:
            for _, r in logs.iterrows():
                with st.chat_message("user"):
                    st.write(f"**{r['teacher_name']} ({r['subject']})**")
                    st.write(r['content'])

# ==========================================
# 6. 로그인 페이지
# ==========================================
def login_page():
    st.markdown("<br><br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([0.1, 1, 0.1]) 
    with c2:
        with st.container(border=True):
            st.markdown('<div class="main-title">온탑영어펀한수학학원</div>', unsafe_allow_html=True)
            with st.form("login"):
                st.write("### 로그인")
                uid = st.text_input("아이디")
                upw = st.text_input("비밀번호", type="password")
                if st.form_submit_button("접속", use_container_width=True):
                    # 탭: users
                    users = load_data('users', ['id', 'pw', 'name', 'role', 'class_group', 'linked_student', 'subject', 'math_class', 'eng_class'])
                    hpw = make_hashes(upw)
                    user = users[(users['id'] == uid) & (users['pw'] == hpw)]
                    if user.empty:
                        user = users[(users['id'] == uid) & (users['pw'] == str(upw))]
                        if not user.empty:
                            users.at[user.index[0], 'pw'] = hpw
                            save_data('users', users)
                    if not user.empty:
                        st.session_state['logged_in'] = True
                        st.session_state['user_id'] = user.iloc[0]['id']
                        st.session_state['user_role'] = user.iloc[0]['role']
                        st.session_state['user_name'] = user.iloc[0]['name']
                        st.session_state['user_subject'] = user.iloc[0]['subject']
                        st.session_state['linked_student'] = user.iloc[0]['linked_student']
                        st.rerun()
                    else: st.error("정보 불일치")
        st.caption("초기계정: admin(원장), t_eng(영어쌤), t_math(수학쌤), student1(학생), parent1(부모) / 비번 1234")

# ==========================================
# 7. 선생님 페이지
# ==========================================
def teacher_page():
    st.markdown(f"### 👨‍🏫 {st.session_state['user_name']} 선생님")
    tabs = st.tabs(["📝 학습 기록", "📓 단어장 관리", "👥 구성원 관리", "📊 성적 관리", "⚙️ 시험지 관리"])
    
    with tabs[0]: # 학습 기록
        users = load_data('users', ['id', 'name', 'role', 'math_class', 'eng_class'])
        stds = users[users['role']=='student']
        c1, c2 = st.columns(2)
        target = c1.selectbox("학생 선택", stds['id'], format_func=lambda x: f"{stds[stds['id']==x]['name'].values[0]} ({x})", key="sel_std_log")
        with st.expander("📅 학습 달력 보기", expanded=True): render_calendar(target)
        st.divider()
        date = c2.date_input("날짜", datetime.now(), key="log_date")
        content = st.text_area("내용", height=100, key="log_content")
        if st.button("저장", type="primary", use_container_width=True, key="btn_save_log"):
            if content:
                # 탭: learning_log
                log = load_data('learning_log', ['student_id', 'date', 'content', 'teacher_name', 'subject'])
                new = pd.DataFrame([{'student_id': target, 'date': str(date), 'content': content, 'teacher_name': st.session_state['user_name'], 'subject': st.session_state['user_subject']}])
                save_data('learning_log', pd.concat([log, new], ignore_index=True))
                st.success("완료"); st.rerun()
        st.write(f"##### 📋 {date} 기록 관리")
        log_df = load_data('learning_log', ['student_id', 'date', 'content', 'teacher_name', 'subject'])
        mask = (log_df['student_id'] == target) & (log_df['date'] == str(date))
        if not log_df[mask].empty:
            edited = st.data_editor(log_df[mask], num_rows="dynamic", use_container_width=True, hide_index=True, key="edit_log_table")
            if st.button("수정사항 저장", key="btn_edit_log"):
                log_df = log_df[~mask]
                log_df = pd.concat([log_df, edited], ignore_index=True)
                save_data('learning_log', log_df)
                st.success("수정됨"); st.rerun()
        else: st.info("기록 없음")

    with tabs[1]: # 단어장
        st.write("##### 📥 단어장 업로드")
        file = st.file_uploader("파일", type=['pdf', 'xlsx', 'csv'], key="up_vocab_file")
        bn = st.text_input("책 이름", key="vocab_book_name")
        if st.button("추가", key="btn_add_vocab"):
            if file and bn:
                extracted_data = []
                current_day_str = "Day 0"
                if file.name.endswith('.pdf'):
                    try:
                        import pdfplumber
                        with pdfplumber.open(file) as pdf:
                            with st.spinner("PDF 분석 중..."):
                                for page in pdf.pages:
                                    width, height = page.width, page.height
                                    bbox_list = [(0, 0, width/2, height), (width/2, 0, width, height)]
                                    for bbox in bbox_list:
                                        text = page.crop(bbox).extract_text() or ""
                                        day_match = re.search(r"DAY\s*(\d+)", text, re.IGNORECASE)
                                        if day_match: current_day_str = f"Day {int(day_match.group(1))}"
                                        matches = re.findall(r"(\d{1,2})\s+([a-zA-Z]+(?:-[a-zA-Z]+)?)\s+(.+)", text)
                                        for _, word, mean in matches:
                                            if len(mean.strip()) > 0: extracted_data.append({'book': bn, 'day': current_day_str, 'word': word.strip(), 'meaning': mean.strip()})
                    except: pass
                elif file.name.endswith(('.xlsx', '.csv')):
                    try:
                        if file.name.endswith('.csv'): df = pd.read_csv(file, dtype=str)
                        else: df = pd.read_excel(file, dtype=str)
                        df.columns = [str(c).lower().strip() for c in df.columns]
                        df = df.rename(columns={'데이': 'day', '단어': 'word', '뜻': 'meaning', '의미': 'meaning'})
                        if {'day', 'word', 'meaning'}.issubset(df.columns):
                            for _, row in df.iterrows(): extracted_data.append({'book': bn, 'day': row['day'], 'word': row['word'], 'meaning': row['meaning']})
                    except: pass
                if extracted_data:
                    # 탭: vocab
                    df_vocab = load_data('vocab', ['book', 'day', 'word', 'meaning'])
                    save_data('vocab', pd.concat([df_vocab, pd.DataFrame(extracted_data)], ignore_index=True))
                    st.success(f"총 {len(extracted_data)}개 저장됨")
        st.divider()
        st.write("##### 📚 책 관리")
        df_v = load_data('vocab', ['book', 'day', 'word', 'meaning'])
        books = sorted(df_v['book'].unique())
        if books:
            c1, c2 = st.columns(2)
            with c1:
                tb = st.selectbox("수정할 책", books, key="sel_book_ren")
                nb = st.text_input("새 이름", value=tb, key="new_book_name")
                if st.button("변경", key="btn_ren_book"):
                    df_v.loc[df_v['book']==tb, 'book'] = nb
                    save_data('vocab', df_v); st.rerun()
            with c2:
                db = st.selectbox("삭제할 책", books, key="sel_book_del")
                if st.button("삭제", key="btn_del_book", type="primary"):
                    save_data('vocab', df_v[df_v['book']!=db]); st.rerun()

    with tabs[2]: # 구성원
        users = load_data('users', ['id', 'pw', 'name', 'role', 'math_class', 'eng_class', 'linked_student', 'subject'])
        if st.session_state['user_id'] == 'admin':
            st.write("##### 👮 선생님 관리")
            teachers = users[users['role'] == 'teacher']
            st.dataframe(teachers[['id', 'name', 'subject']], hide_index=True)
            c1, c2 = st.columns(2)
            with c1:
                with st.expander("수정"):
                    tid = st.selectbox("ID", teachers['id'], key="sel_t_edt")
                    cur = teachers[teachers['id']==tid].iloc[0]
                    with st.form("te_edt"):
                        nn = st.text_input("이름", cur['name'])
                        np = st.text_input("비번")
                        ns = st.text_input("과목", cur['subject'])
                        if st.form_submit_button("저장"):
                            hp = make_hashes(np) if np else cur['pw']
                            users.loc[users['id']==tid, ['name','pw','subject']] = [nn,hp,ns]
                            save_data('users', users); st.rerun()
            with c2:
                with st.expander("삭제/추가"):
                    did = st.selectbox("삭제 ID", teachers['id'], key="sel_t_del")
                    if st.button("삭제", key="btn_del_teacher"):
                        if did != 'admin': save_data('users', users[users['id']!=did]); st.rerun()
                    st.divider()
                    st.write("신규 추가")
                    nid = st.text_input("ID", key="new_t_id")
                    npw = st.text_input("PW", key="new_t_pw")
                    nname = st.text_input("이름", key="new_t_nm")
                    nsubj = st.text_input("과목", key="new_t_sub")
                    if st.button("추가", key="btn_add_teacher"):
                        if nid not in users['id'].values:
                             new = pd.DataFrame([{'id': nid, 'pw': make_hashes(npw), 'name': nname, 'role': 'teacher', 'subject': nsubj, 'math_class':'', 'eng_class':'', 'linked_student':''}])
                             save_data('users', pd.concat([users, new], ignore_index=True)); st.rerun()

        st.divider()
        st.write("##### 👥 학생 관리")
        stds = users[users['role'] == 'student']
        st.dataframe(stds[['id', 'name', 'math_class', 'eng_class']], hide_index=True)
        c1, c2 = st.columns(2)
        with c1:
            with st.expander("✏️ 학생 수정"):
                if not stds.empty:
                    sid = st.selectbox("ID", stds['id'], key="sel_s_edt")
                    sc = stds[stds['id']==sid].iloc[0]
                    with st.form("se_edt"):
                        nn = st.text_input("이름", sc['name'])
                        np = st.text_input("비번")
                        nm = st.text_input("수학반", sc['math_class'])
                        ne = st.text_input("영어반", sc['eng_class'])
                        if st.form_submit_button("저장"):
                            hp = make_hashes(np) if np else sc['pw']
                            users.loc[users['id']==sid, ['name','pw','math_class','eng_class']] = [nn,hp,nm,ne]
                            save_data('users', users); st.rerun()
        with c2:
            with st.expander("🗑️ 학생 삭제"):
                if not stds.empty:
                    dsid = st.selectbox("삭제ID", stds['id'], key="sel_s_del")
                    if st.button("삭제", key="btn_del_student"):
                        save_data('users', users[users['id']!=dsid]); st.rerun()
                        
        st.divider()
        st.write("##### 👪 학부모 관리")
        parents = users[users['role'] == 'parent']
        st.dataframe(parents[['id', 'name', 'linked_student']], hide_index=True)
        c1, c2 = st.columns(2)
        with c1:
            with st.expander("✏️ 학부모 수정"):
                if not parents.empty:
                    pid = st.selectbox("ID", parents['id'], key="sel_p_edt")
                    pc = parents[parents['id']==pid].iloc[0]
                    with st.form("pe_edt"):
                        nn = st.text_input("이름", pc['name'])
                        np = st.text_input("비번")
                        nl = st.text_input("자녀ID", pc['linked_student'])
                        if st.form_submit_button("저장"):
                            hp = make_hashes(np) if np else pc['pw']
                            users.loc[users['id']==pid, ['name','pw','linked_student']] = [nn,hp,nl]
                            save_data('users', users); st.rerun()
        with c2:
             with st.expander("🗑️ 학부모 삭제"):
                if not parents.empty:
                    dpid = st.selectbox("삭제ID", parents['id'], key="sel_p_del")
                    if st.button("삭제", key="btn_del_parent"):
                        save_data('users', users[users['id']!=dpid]); st.rerun()

        with st.expander("➕ 계정 생성", expanded=True):
            r = st.selectbox("구분", ['student', 'parent', 'teacher'], key="new_role")
            i = st.text_input("ID", key="new_id")
            p = st.text_input("PW", key="new_pw")
            n = st.text_input("이름", key="new_name")
            c = st.text_input("반/과목", key="new_cls")
            l = st.text_input("자녀ID", key="new_lnk")
            if st.button("생성", key="btn_create_user"):
                if i not in users['id'].values:
                    new = pd.DataFrame([{'id': i, 'pw': make_hashes(p), 'name': n, 'role': r, 'math_class': c if r=='student' else '', 'eng_class': c if r=='student' else '', 'subject': c if r=='teacher' else '', 'linked_student': l}])
                    save_data('users', pd.concat([users, new], ignore_index=True)); st.success("완료")
                else: st.error("중복")

    with tabs[3]: # 성적 관리
        sub_t1, sub_t2, sub_t3 = st.tabs(["💯 점수 입력", "📒 단어 시험 결과", "🖨️ 오답 단어지 다운"])
        
        with sub_t1:
            st.write("##### 📊 반별 성적")
            # 탭: score
            df_score = load_data('score', ['student_id', 'exam_name', 'subject', 'score', 'date'])
            df_users = load_data('users', ['id', 'name', 'math_class', 'eng_class'])
            
            merged_df = pd.merge(df_score, df_users[['id', 'name', 'math_class', 'eng_class']], left_on='student_id', right_on='id', how='left')
            math_classes = set(merged_df['math_class'].astype(str))
            eng_classes = set(merged_df['eng_class'].astype(str))
            all_classes_raw = math_classes | eng_classes
            all_classes = sorted([c for c in all_classes_raw if c and c.lower() != 'nan' and c.lower() != 'none'])
            
            selected_class = st.selectbox("반 선택", ["전체 보기"] + all_classes, key="sel_class_avg")
            
            if selected_class != "전체 보기":
                view_df = merged_df[(merged_df['math_class'] == selected_class) | (merged_df['eng_class'] == selected_class)]
            else:
                view_df = merged_df
                
            if not view_df.empty and 'subject' in view_df.columns:
                final_view = view_df[['name', 'exam_name', 'subject', 'score']].copy()
                final_view.columns = ['이름', '시험명', '과목', '점수']
                st.dataframe(final_view, use_container_width=True)
                
                try:
                    view_df['score'] = pd.to_numeric(view_df['score'], errors='coerce')
                    avg_score = view_df.groupby(['exam_name', 'subject'])['score'].mean().reset_index()
                    avg_score.columns = ['시험명', '과목', '평균점수']
                    st.write("📈 **선택된 반 평균 점수**")
                    st.dataframe(avg_score, use_container_width=True)
                except: pass
            else: st.info("데이터 없음")

            st.divider()
            st.write("##### 📝 점수 입력")
            stds = users[users['role'] == 'student']
            with st.form("add_score"):
                c1, c2, c3 = st.columns(3)
                s_id = c1.selectbox("학생", stds['id'], format_func=lambda x: f"{stds[stds['id']==x]['name'].values[0]} ({x})")
                s_subj = c2.selectbox("과목", ["수학", "영어"])
                s_date = c3.date_input("날짜", datetime.now())
                s_exam = st.text_input("시험명")
                s_score = st.number_input("점수", 0, 100)
                if st.form_submit_button("추가"):
                    new_row = pd.DataFrame([{'student_id': s_id, 'exam_name': s_exam, 'subject': s_subj, 'score': str(s_score), 'date': str(s_date)}])
                    save_data('score', pd.concat([df_score, new_row], ignore_index=True)); st.success("추가됨"); st.rerun()
            
            st.caption("점수 수정/삭제")
            if not df_score.empty:
                df_display = pd.merge(df_score, stds[['id', 'name']], left_on='student_id', right_on='id', how='left')
                edited_scores = st.data_editor(
                    df_display[['student_id', 'name', 'exam_name', 'subject', 'score', 'date']],
                    column_config={
                        "student_id": st.column_config.TextColumn("ID", disabled=True),
                        "name": st.column_config.TextColumn("이름", disabled=True),
                        "exam_name": "시험명", "subject": "과목", "score": "점수", "date": "날짜"
                    },
                    use_container_width=True, num_rows="dynamic", key="score_editor"
                )
                if st.button("점수 변경사항 저장", key="btn_save_scores"):
                    save_df = edited_scores[['student_id', 'exam_name', 'subject', 'score', 'date']]
                    save_data('score', save_df); st.success("저장됨"); st.rerun()

        with sub_t2:
            st.write("##### 📖 단어 테스트 기록")
            # 탭: vocab_test_log
            df_test = load_data('vocab_test_log', ['student_id', 'date', 'info', 'score'])
            if not df_test.empty:
                df_test = pd.merge(df_test, stds[['id', 'name']], left_on='student_id', right_on='id', how='left')
                st.dataframe(df_test[['date', 'name', 'info', 'score']], use_container_width=True)
            else: st.info("기록 없음")

        with sub_t3:
            st.write("##### 🖨️ 오답 시험지 다운로드 (Excel/CSV)")
            target_s = st.selectbox("학생", stds['id'], format_func=lambda x: f"{stds[stds['id']==x]['name'].values[0]} ({x})", key="print_std")
            
            c1, c2 = st.columns(2)
            down_type = c1.radio("출력 대상", ["일반 오답", "누적 테스트 오답"], horizontal=True)
            
            df_vocab = load_data('vocab', ['book', 'word', 'meaning'])
            paper_data = pd.DataFrame()

            if down_type == "일반 오답":
                # 탭: vocab_prog
                df_prog = load_data('vocab_prog', ['student_id', 'book', 'word', 'status'])
                my_wrongs = df_prog[(df_prog['student_id'] == target_s) & (df_prog['status'] == 'learning')]
                if not my_wrongs.empty:
                     paper_data = pd.merge(my_wrongs, df_vocab, on=['book', 'word'], how='left')[['book', 'word', 'meaning']]
            else:
                # 탭: vocab_test_wrongs
                df_tw = load_data('vocab_test_wrongs', ['student_id', 'book', 'word'])
                my_wrongs = df_tw[df_tw['student_id'] == target_s]
                if not my_wrongs.empty:
                    paper_data = pd.merge(my_wrongs, df_vocab, on=['book', 'word'], how='left')[['book', 'word', 'meaning']]
            
            if paper_data.empty: st.info("오답 없음")
            else:
                st.write(f"총 {len(paper_data)}개")
                words = paper_data['word'].tolist()
                meanings = paper_data['meaning'].tolist()
                mid = math.ceil(len(words) / 2)
                col1_w = words[:mid]; col1_m = meanings[:mid]
                col2_w = words[mid:] + [''] * (mid - len(words[mid:]))
                col2_m = meanings[mid:] + [''] * (mid - len(meanings[mid:]))
                print_df = pd.DataFrame({'단어1': col1_w, '뜻1': col1_m, '공백': [''] * mid, '단어2': col2_w, '뜻2': col2_m})
                csv = print_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 2단 단어장 다운로드", csv, f"{target_s}_print.csv", "text/csv")

    with tabs[4]: # 시험지 관리
        st.write("##### 📤 시험지 등록")
        en = st.text_input("시험명", key="new_exam_name")
        ef = st.file_uploader("이미지", accept_multiple_files=True, key="up_exam_img")
        if st.button("업로드", key="btn_up_exam"):
            if en and ef:
                # 탭: exam
                dex = load_data('exam', ['시험명', '문제번호', '이미지경로', '영상링크'])
                rows = []
                for f in ef:
                    try:
                        qn = int(f.name.split('.')[0])
                        path = os.path.join(IMAGE_DIR, f"{en}_{qn}.{f.name.split('.')[-1]}")
                        with open(path, "wb") as wb: wb.write(f.getbuffer())
                        rows.append({'시험명': en, '문제번호': qn, '이미지경로': path, '영상링크': ''})
                    except: pass
                save_data('exam', pd.concat([dex, pd.DataFrame(rows)], ignore_index=True)); st.success("완료")
        
        st.divider()
        st.write("##### ✏️ 시험지 정보/링크 수정")
        dex = load_data('exam', ['시험명', '문제번호', '이미지경로', '영상링크'])
        if not dex.empty:
            edit_exam = st.selectbox("수정할 시험 선택", dex['시험명'].unique(), key="sel_edit_exam")
            exam_data = dex[dex['시험명'] == edit_exam].copy()
            exam_data['영상링크'] = exam_data['영상링크'].astype(str)
            exam_data['문제번호'] = pd.to_numeric(exam_data['문제번호'], errors='coerce').fillna(0).astype(int)
            exam_data = exam_data.sort_values('문제번호')

            # 이미지 교체 기능
            st.caption("이미지 교체")
            q_to_change = st.selectbox("교체할 문제 번호", exam_data['문제번호'], key="sel_q_img_chg")
            new_img = st.file_uploader("새 이미지 업로드", type=['png', 'jpg'], key="new_img_file")
            if new_img and st.button("이미지 변경 저장", key="btn_chg_img"):
                target_row = exam_data[exam_data['문제번호'] == q_to_change].iloc[0]
                old_path = target_row['이미지경로']
                # 새 파일 저장
                with open(old_path, "wb") as f: f.write(new_img.getbuffer())
                st.success(f"{q_to_change}번 이미지 교체 완료")
                st.rerun()

            # 이미지 확인
            if st.checkbox("이미지 크게 보기"):
                sel_row = exam_data[exam_data['문제번호'] == q_to_change]
                if not sel_row.empty: st.image(sel_row.iloc[0]['이미지경로'])

            edited_exam_data = st.data_editor(
                exam_data,
                column_config={
                    "이미지경로": st.column_config.TextColumn(disabled=True),
                    "영상링크": st.column_config.LinkColumn(help="유튜브 링크", validate="^https?://.*", max_chars=200),
                    "문제번호": st.column_config.NumberColumn(format="%d", disabled=True)
                },
                use_container_width=True, hide_index=True, key="exam_editor_final"
            )
            if st.button("시험지 수정 저장", key="btn_save_exam_edit_final"):
                dex = dex[dex['시험명'] != edit_exam]
                edited_exam_data['문제번호'] = edited_exam_data['문제번호'].astype(str)
                save_data('exam', pd.concat([dex, edited_exam_data], ignore_index=True))
                st.success("수정됨"); st.rerun()

            st.write("##### 🗑️ 시험지 삭제")
            if st.button("선택한 시험지 전체 삭제", key="btn_del_exam_all", type="primary"):
                dex = dex[dex['시험명'] != edit_exam]
                save_data('exam', dex); st.success("삭제됨"); st.rerun()
        else: st.info("등록된 시험지 없음")

# ==========================================
# 8. 학생 페이지
# ==========================================
def student_page(user_id):
    st.markdown(f"### 👋 {st.session_state['user_name']} 학생")
    tabs = st.tabs(["📅 학습 일지", "🧠 단어 암기", "📝 오답 체크", "📂 오답노트", "📈 성적표"]) 
    
    with tabs[0]: render_calendar(user_id)
    with tabs[1]: vocab_study_session(user_id)
    
    with tabs[2]:
        st.write("##### 📝 시험지 오답 체크")
        # 탭: exam
        df_exam = load_data('exam', ['시험명', '문제번호', '이미지경로', '영상링크'])
        # 탭: mynote
        df_note = load_data('mynote', ['학생이름', '시험명', '문제번호', '메모'])
        
        if df_exam.empty: st.info("시험지 없음")
        else:
            sel_exam = st.selectbox("시험지 선택", df_exam['시험명'].unique(), key="std_sel_exam")
            exam_data = df_exam[df_exam['시험명'] == sel_exam]
            exam_data['문제번호'] = pd.to_numeric(exam_data['문제번호'])
            q_nums = sorted(exam_data['문제번호'].unique())
            
            with st.form("wrong_check_form"):
                st.write(f"**{sel_exam}** 틀린 문제 선택")
                picks = st.multiselect("문제 번호", q_nums)
                memo = st.text_area("메모")
                if st.form_submit_button("저장"):
                    new_notes = []
                    for q in picks:
                        if not ((df_note['학생이름']==user_id) & (df_note['시험명']==sel_exam) & (df_note['문제번호']==str(q))).any():
                            new_notes.append({'학생이름': user_id, '시험명': sel_exam, '문제번호': str(q), '메모': memo})
                    if new_notes:
                        save_data('mynote', pd.concat([df_note, pd.DataFrame(new_notes)], ignore_index=True))
                        st.success("저장됨")
                    else: st.warning("이미 저장됨")

    with tabs[3]:
        st.write("##### 📂 내 오답노트")
        dn = load_data('mynote', ['학생이름', '시험명', '문제번호', '메모'])
        de = load_data('exam', ['시험명', '문제번호', '이미지경로', '영상링크'])
        mn = dn[dn['학생이름'] == user_id]
        if mn.empty: st.info("오답노트 비어있음")
        else:
            for ex in mn['시험명'].unique():
                with st.expander(f"📑 {ex}", expanded=False):
                    ex_notes = mn[mn['시험명']==ex]
                    for _, r in ex_notes.iterrows():
                        st.markdown(f"**Q.{r['문제번호']}**")
                        qd = de[(de['시험명']==ex) & (de['문제번호']==str(r['문제번호']))]
                        if not qd.empty:
                            try: st.image(qd.iloc[0]['이미지경로'])
                            except: pass
                            if qd.iloc[0]['영상링크']:
                                # [FIX] 유튜브 시간 재생
                                t_sec = get_yt_start_time(qd.iloc[0]['영상링크'])
                                with st.expander("🎬 해설 보기"): st.video(qd.iloc[0]['영상링크'], start_time=t_sec)
                        st.info(f"메모: {r['메모']}")
                        if st.button("삭제", key=f"del_note_{r.name}"):
                            dn = dn.drop(r.name)
                            save_data('mynote', dn); st.rerun()
                        st.divider()
    with tabs[4]:
        sc = load_data('score', ['student_id', 'exam_name', 'subject', 'score', 'date'])
        my = sc[sc['student_id']==user_id].copy()
        if not my.empty:
            my['score'] = pd.to_numeric(my['score'], errors='coerce')
            st.dataframe(my[['date', 'exam_name', 'subject', 'score']], use_container_width=True)
            for s in my['subject'].unique(): 
                sub_data = my[my['subject']==s].sort_values('date')
                st.line_chart(sub_data, x='exam_name', y='score')
        else: st.info("기록 없음")

def parent_page(user_id, linked_std):
    st.markdown(f"### 👪 {st.session_state['user_name']}님 (자녀: {linked_std})")
    if not linked_std: st.error("자녀 없음"); return
    tabs = st.tabs(["📅 학습일지", "📈 성적표", "💯 단어테스트", "📂 오답노트"])
    with tabs[0]: render_calendar(linked_std)
    with tabs[1]:
        sc = load_data('score', ['student_id', 'exam_name', 'subject', 'score', 'date'])
        my = sc[sc['student_id']==linked_std]
        st.dataframe(my, use_container_width=True)
    with tabs[2]:
        st.markdown("##### 📕 자녀 단어 누적 테스트 결과")
        df_test = load_data('vocab_test_log', ['student_id', 'date', 'info', 'score'])
        my_test = df_test[df_test['student_id'] == linked_std]
        st.dataframe(my_test, use_container_width=True)
    with tabs[3]:
        df = load_data('mynote', ['학생이름', '시험명', '문제번호', '메모'])
        st.dataframe(df[df['학생이름']==linked_std], use_container_width=True)

# ==========================================
# 7. 실행 컨트롤러
# ==========================================
if not st.session_state['logged_in']:
    login_page()
else:
    with st.sidebar:
        st.info(f"{st.session_state['user_name']} ({st.session_state['user_role']})")
        
        # [NEW] 새로고침 버튼 추가
        if st.button("🔄 새로고침 (데이터 갱신)", use_container_width=True):
            st.rerun()
        
        st.divider() # 구분선
        
        if st.button("로그아웃", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()

    role = st.session_state['user_role']
    if role == 'teacher':
        teacher_page()
    elif role == 'parent':
        parent_page(st.session_state['user_id'], st.session_state['linked_student'])
    else:
        student_page(st.session_state['user_id'])
