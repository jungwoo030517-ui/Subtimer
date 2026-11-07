#%%
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

# --- Streamlit 웹 UI 및 스타일 설정 ---
st.set_page_config(page_title="노포 환승 타이머", page_icon="🚇")

# 🎨 UI 글자 및 숫자 크기 지정을 위한 Custom CSS (강제 적용 버전)
st.markdown("""
    <style>
    /* 1. 시간 선택창(stSelectbox) 내부의 모든 텍스트, 숫자, 입력창 크기 강제 지정 */
    div[data-testid="stSelectbox"] * {
        font-size: 1.5rem !important;
        font-weight: bold !important;
    }

    /* 2. 클릭했을 때 열리는 선택 목록(드롭다운 메뉴) 글자 크기 */
    div[data-baseweb="popover"] * {
        font-size: 1.5rem !important;
    }

    /* 3. '희망하는 1144번 버스 출발 시간' 라벨(제목) 크기 조절 (너무 커지는 것 방지) */
    div[data-testid="stSelectbox"] label p {
        font-size: 1.1rem !important;
        font-weight: medium !important;
    }

    /* 4. 환승 여유 시간 슬라이더 텍스트/숫자 크기 */
    div[data-testid="stSlider"] * {
        font-size: 1.2rem !important;
        font-weight: medium !important;
    }

    /* 5. 버튼 글자 크기 */
    div.stButton > button * {
        font-size: 1.15rem !important;
        font-weight: bold !important;
    }
    </style>
""", unsafe_allow_html=True)

# 1. 역간 소요시간 계산 (run time.csv)
@st.cache_data
def get_travel_time(start_station, end_station, filepath='run time.csv'):
    df = pd.read_csv(filepath, encoding='cp949') 
    
    start_idx = df.index[df['역명'].str.contains(start_station)].tolist()[0]
    end_idx = df.index[df['역명'].str.contains(end_station)].tolist()[0]
    
    s_idx, e_idx = min(start_idx, end_idx), max(start_idx, end_idx)
    
    total_seconds = 0
    for t in df.iloc[s_idx+1:e_idx+1]['소요시간(분)']:
        m, s = map(int, str(t).split(':'))
        total_seconds += m * 60 + s
        
    return timedelta(seconds=total_seconds)

# 2. 노포역 버스 출발시간 추출 (1144.xlsx)
@st.cache_data
def get_bus_times(filepath='1144.xlsx'):
    df = pd.read_excel(filepath)
    
    idx_after = df[df.iloc[:, 0].astype(str).str.contains('변경 후', na=False)].index
    start_row = idx_after[0] if len(idx_after) > 0 else 0
    
    bus_times = []
    for i in range(start_row + 2, len(df)):
        for j in range(len(df.columns)):
            if '노포' in str(df.iloc[start_row + 1, j]):
                val = df.iloc[i, j]
                if pd.notna(val):
                    if isinstance(val, str):
                        bus_times.append(val)
                    else:
                        bus_times.append(val.strftime('%H:%M'))
                        
    return sorted(list(set(bus_times)))

# 3. 요일별 지하철 시간표 로드
@st.cache_data
def get_subway_times(day_type):
    file_map = {
        "평일": "Seomyeon1_ToNopo_WK.csv",
        "토요일": "Seomyeon1_ToNopo_SA.csv",
        "공휴일": "Seomyeon1_ToNopo_WE.csv"
    }
    filepath = file_map[day_type]
    
    try:
        df = pd.read_csv(filepath, header=None)
        return df[0].astype(str).str.strip().tolist()
    except FileNotFoundError:
        st.error(f"❌ {filepath} 파일이 없어! 파일 위치와 이름을 확인해줘.")
        return []

# 4. 역산 최적 탑승 시간 계산 로직
def find_optimal_subway(target_bus_time, subway_times, travel_time, buffer_mins=3):
    if not subway_times:
        return None, None
        
    bus_h, bus_m = map(int, target_bus_time.split(':'))
    if bus_h < 4:
        bus_h += 24
    bus_td = timedelta(hours=bus_h, minutes=bus_m)
    
    buffer_td = timedelta(minutes=buffer_mins)
    max_arrival_td = bus_td - buffer_td
    max_departure_td = max_arrival_td - travel_time
    
    valid_trains = []
    for st_time in subway_times:
        st_h, st_m = map(int, st_time.split(':'))
        if st_h < 4:
            st_h += 24
        st_td = timedelta(hours=st_h, minutes=st_m)
        
        if st_td <= max_departure_td:
            valid_trains.append((st_time, st_td))
            
    if valid_trains:
        optimal_train = max(valid_trains, key=lambda x: x[1])
        optimal_time = optimal_train[0]
        
        arrive_td = optimal_train[1] + travel_time
        arr_h = int(arrive_td.total_seconds() // 3600) % 24
        arr_m = int((arrive_td.total_seconds() % 3600) // 60)
        arr_s = int(arrive_td.total_seconds() % 60)
        arrive_time_str = f"{arr_h:02d}:{arr_m:02d}:{arr_s:02d}"
        
        return optimal_time, arrive_time_str
    return None, None

# --- UI 본문 ---
st.title("🚇 지하철 언제 탈지 알려드림")

try:
    travel_time = get_travel_time('서면', '노포')
    bus_times = get_bus_times('1144.xlsx')
    st.write(f"**서면 ➔ 노포 지하철 소요시간**: {travel_time.seconds // 60}분 {travel_time.seconds % 60}초")
except Exception as e:
    st.error("기본 데이터(run time.csv 또는 1144.xlsx)를 불러오는 데 실패했어.")
    st.stop()

# session_state 초기화
if "target_bus" not in st.session_state:
    st.session_state.target_bus = bus_times[0]

day_type = st.radio("요일을 선택해", ["평일", "토요일", "공휴일"], horizontal=True)
subway_times = get_subway_times(day_type)

# 🕒 현재 시각 기준 가장 빠른 버스 찾기 버튼
if st.button("🕒 지금 시각 기준 가장 빠른 버스 맞추기", use_container_width=True):
    now = datetime.now()
    estimated_arrival = now + travel_time + timedelta(minutes=3)
    
    next_bus = None
    for b in bus_times:
        b_h, b_m = map(int, b.split(':'))
        b_dt = now.replace(hour=b_h, minute=b_m, second=0, microsecond=0)
        if b_dt >= estimated_arrival:
            next_bus = b
            break
            
    if next_bus:
        st.session_state.target_bus = next_bus
        st.toast(f"현재 시각({now.strftime('%H:%M')}) 기준 탑승 가능한 {next_bus} 버스로 맞췄어!", icon="⏱️")
    else:
        st.warning("오늘 운행하는 남은 버스가 없어!")

col1, col2 = st.columns(2)
with col1:
    target_bus = st.selectbox(
        "희망하는 1144번 버스 출발 시간", 
        bus_times, 
        index=bus_times.index(st.session_state.target_bus) if st.session_state.target_bus in bus_times else 0,
        key="bus_select"
    )
    st.session_state.target_bus = target_bus

with col2:
    # 🎛️ 스크롤/드래그 방식의 슬라이더 (1분 ~ 10분 설정)
    buffer_mins = st.slider(
        "환승 여유 시간", 
        min_value=1, 
        max_value=10, 
        value=3, 
        step=1,
        format="%d분"
    )

if st.button("최적 지하철 찾기", type="primary", use_container_width=True):
    optimal, arrive = find_optimal_subway(target_bus, subway_times, travel_time, buffer_mins)
    
    if optimal:
        st.success(f"✅ 늦어도 **{optimal}** 열차를 타야 해!")
        st.markdown(f"""
        * 🚇 **서면역 탑승:** {optimal}
        * 🚩 **노포역 도착:** {arrive}
        * 🚌 **버스 출발:** {target_bus} (여유시간 {buffer_mins}분)
        """)
    else:
        st.error("❌ 이 버스를 타기 위한 지하철 다이어가 부족해. 첫차 시간 등을 확인해봐.")
