import streamlit as st
import chromadb
import math
import json
from collections import defaultdict
from core.config import CHROMA_HOST, CHROMA_PORT

PAGE_SIZE = 50  # 한 페이지당 문서 개수

st.set_page_config(page_title="ChromaDB Viewer", layout="wide")
st.title("ChromaDB 컬렉션 뷰어 (페이지별, 그룹화 보기)")

# ChromaDB 연결
try:
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collections = client.list_collections()
    if not collections:
        st.warning("컬렉션이 없습니다. ChromaDB에 데이터가 있는지 확인하세요.")
        st.stop()
    st.success(f"연결 성공: {len(collections)}개 컬렉션 탐색됨")
except Exception as e:
    st.error(f"연결 실패: {e}")
    st.stop()

# 컬렉션 선택
selected = st.selectbox("컬렉션 선택", [c.name for c in collections])

# 문서 페이지네이션 및 그룹화
if selected:
    col = client.get_collection(name=selected)

    try:
        data = col.get()  # 전체 데이터 불러오기
        ids = data.get("ids", [])
        docs = data.get("documents", [])
        metas = data.get("metadatas", [])

        total_docs = len(docs)
        if total_docs == 0:
            st.warning("이 컬렉션에는 문서가 없습니다.")
            st.stop()

        # restaurant_id 기준으로 그룹화
        grouped = defaultdict(list)
        for i in range(total_docs):
            meta = metas[i] if metas and i < len(metas) else {}
            restaurant_id = meta.get("restaurant_id", f"no_id_{i}")
            grouped[restaurant_id].append({
                "id": ids[i],
                "doc": docs[i],
                "meta": meta
            })

        # 페이지 상태 관리
        if "page" not in st.session_state:
            st.session_state.page = 1

        total_groups = len(grouped)
        total_pages = math.ceil(total_groups / PAGE_SIZE)
        group_keys = list(grouped.keys())
        start = (st.session_state.page - 1) * PAGE_SIZE
        end = start + PAGE_SIZE

        # 이전 / 다음 버튼
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if st.button("⬅ 이전 페이지") and st.session_state.page > 1:
                st.session_state.page -= 1
        with col3:
            if st.button("다음 페이지 ➡") and st.session_state.page < total_pages:
                st.session_state.page += 1

        st.write(f"📄 현재 페이지: {st.session_state.page} / {total_pages}")

        # --- 그룹별 문서 출력 (기본 열림) ---
        for key in group_keys[start:end]:
            group_docs = grouped[key]
            restaurant_name = group_docs[0]['meta'].get("name", "이름 없음") if group_docs[0]['meta'] else "이름 없음"

            with st.expander(f"{restaurant_name} (ID {key}) - {len(group_docs)} 문서", expanded=True):
                for d in group_docs:
                    st.markdown(f"문서 ID: {d['id']}")
                    st.markdown(f"내용: {d['doc']}")
                    if d['meta']:
                        st.json(d['meta'])

        # --- 전체 데이터 다운로드 ---
        st.download_button(
            label="⬇전체 데이터 JSON 다운로드",
            data=json.dumps(data, ensure_ascii=False, indent=2),
            file_name=f"{selected}_all_docs.json",
            mime="application/json"
        )

    except Exception as e:
        st.error(f"데이터 조회 오류: {e}")
