import uuid

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


st.set_page_config(
    page_title="Agent-Pilot",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --brand: #7c5cff;
        --brand-soft: rgba(124, 92, 255, 0.14);
        --surface: #151822;
        --surface-soft: #1c2030;
    }
    [data-testid="stSidebar"] {
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }
    [data-testid="stSidebar"] h1 {
        letter-spacing: -0.04em;
        margin-bottom: 0.25rem;
    }
    [data-testid="stSidebar"] .stButton > button {
        border-radius: 0.75rem;
        min-height: 2.55rem;
        transition: border-color 120ms ease, background 120ms ease;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        border-color: var(--brand);
        background: var(--brand-soft);
    }
    [data-testid="stFileUploader"] {
        border: 1px dashed rgba(124, 92, 255, 0.7);
        border-radius: 0.9rem;
        background: var(--brand-soft);
        padding: 0.35rem;
    }
    [data-testid="stChatInput"] {
        border-radius: 1rem;
    }
    .workspace-kicker {
        color: #a6a9ba;
        font-size: 0.95rem;
        margin-top: -0.65rem;
        margin-bottom: 1.25rem;
    }
    .empty-state {
        border: 1px solid rgba(124, 92, 255, 0.28);
        border-radius: 1rem;
        background: linear-gradient(135deg, var(--brand-soft), rgba(255,255,255,0.02));
        padding: 2.2rem 2rem;
        margin: 2rem 0 1.5rem;
    }
    .empty-state h3 { margin: 0 0 0.45rem; }
    .empty-state p { color: #a6a9ba; margin: 0; }
    .sidebar-label {
        color: #a6a9ba;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin: 1.35rem 0 0.45rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

from langraph_rag_backend import (
    chatbot,
    ingest_pdf,
    retrieve_all_threads,
    thread_document_metadata,
)


# =========================== Utilities ===========================
def generate_thread_id():
    return uuid.uuid4()


def reset_chat():
    thread_id = generate_thread_id()
    st.session_state["thread_id"] = thread_id
    add_thread(thread_id)
    st.session_state["thread_titles"][str(thread_id)] = f"New chat · {str(thread_id)[:8]}"
    st.session_state["message_history"] = []


def add_thread(thread_id):
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state["chat_threads"].append(thread_id)


def load_conversation(thread_id):
    state = chatbot.get_state(config={"configurable": {"thread_id": thread_id}})
    return state.values.get("messages", [])


def conversation_title(thread_id):
    """Create a readable sidebar title from the first user message."""
    for message in load_conversation(thread_id):
        if isinstance(message, HumanMessage) and message.content:
            title = " ".join(str(message.content).split())
            return title[:45] + ("..." if len(title) > 45 else "")
    return f"New chat · {str(thread_id)[:8]}"


# ======================= Session Initialization ===================
if "message_history" not in st.session_state:
    st.session_state["message_history"] = []

if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = generate_thread_id()

if "chat_threads" not in st.session_state:
    st.session_state["chat_threads"] = retrieve_all_threads()

if "ingested_docs" not in st.session_state:
    st.session_state["ingested_docs"] = {}

if "thread_titles" not in st.session_state:
    st.session_state["thread_titles"] = {
        str(thread_id): conversation_title(thread_id)
        for thread_id in st.session_state["chat_threads"]
    }

add_thread(st.session_state["thread_id"])

thread_key = str(st.session_state["thread_id"])
thread_docs = st.session_state["ingested_docs"].setdefault(thread_key, {})
threads = st.session_state["chat_threads"][::-1]
selected_thread = None

# ============================ Sidebar ============================
st.sidebar.title("Agent-Pilot")
st.sidebar.caption("Your intelligent document workspace")

if st.sidebar.button("New Chat", use_container_width=True):
    reset_chat()
    st.rerun()

if thread_docs:
    latest_doc = list(thread_docs.values())[-1]
    st.sidebar.success(
        f"📄 `{latest_doc.get('filename')}`\n\n"
        f"{latest_doc.get('chunks')} chunks · {latest_doc.get('documents')} pages"
    )
else:
    st.sidebar.info("Upload a PDF to ground your answers in its content.")

st.sidebar.markdown('<div class="sidebar-label">Knowledge source</div>', unsafe_allow_html=True)
uploaded_pdf = st.sidebar.file_uploader("Upload a PDF", type=["pdf"], label_visibility="collapsed")
if uploaded_pdf:
    if uploaded_pdf.name in thread_docs:
        st.sidebar.info(f"`{uploaded_pdf.name}` already processed for this chat.")
    else:
        with st.sidebar.status("Indexing PDF…", expanded=True) as status_box:
            summary = ingest_pdf(
                uploaded_pdf.getvalue(),
                thread_id=thread_key,
                filename=uploaded_pdf.name,
            )
            thread_docs[uploaded_pdf.name] = summary
            status_box.update(label="✅ PDF indexed", state="complete", expanded=False)

st.sidebar.markdown('<div class="sidebar-label">Recent conversations</div>', unsafe_allow_html=True)
if not threads:
    st.sidebar.write("No past conversations yet.")
else:
    for thread_id in threads:
        thread_title = st.session_state["thread_titles"].get(
            str(thread_id), conversation_title(thread_id)
        )
        if st.sidebar.button(
            thread_title,
            key=f"side-thread-{thread_id}",
            help=f"Thread ID: {thread_id}",
            use_container_width=True,
        ):
            selected_thread = thread_id

# ============================ Main Layout ========================
st.title("Agent-Pilot")
st.markdown(
    '<div class="workspace-kicker">Ask questions, explore documents, and get grounded answers.</div>',
    unsafe_allow_html=True,
)

if not st.session_state["message_history"]:
    st.markdown(
        """
        <div class="empty-state">
            <h3>What would you like to explore?</h3>
            <p>Upload a PDF in the sidebar, then ask a question about it. You can also use the assistant for calculations and web lookups.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Chat area
for message in st.session_state["message_history"]:
    with st.chat_message(message["role"]):
        st.text(message["content"])

user_input = st.chat_input("Ask about your document or use tools")

if user_input:
    if not st.session_state["message_history"]:
        title = " ".join(user_input.split())
        st.session_state["thread_titles"][thread_key] = title[:45] + (
            "..." if len(title) > 45 else ""
        )
    st.session_state["message_history"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.text(user_input)

    CONFIG = {
        "configurable": {"thread_id": thread_key},
        "metadata": {"thread_id": thread_key},
        "run_name": "chat_turn",
    }

    with st.chat_message("assistant"):
        status_holder = {"box": None}

        def ai_only_stream():
            for message_chunk, _ in chatbot.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config=CONFIG,
                stream_mode="messages",
            ):
                if isinstance(message_chunk, ToolMessage):
                    tool_name = getattr(message_chunk, "name", "tool")
                    if status_holder["box"] is None:
                        status_holder["box"] = st.status(
                            f"🔧 Using `{tool_name}` …", expanded=True
                        )
                    else:
                        status_holder["box"].update(
                            label=f"🔧 Using `{tool_name}` …",
                            state="running",
                            expanded=True,
                        )

                if isinstance(message_chunk, AIMessage):
                    yield message_chunk.content

        try:
            ai_message = st.write_stream(ai_only_stream())
        except RuntimeError as exc:
            st.error(str(exc))
            ai_message = "I could not complete that request because the chat provider is not configured."

        if status_holder["box"] is not None:
            status_holder["box"].update(
                label="✅ Tool finished", state="complete", expanded=False
            )

    st.session_state["message_history"].append(
        {"role": "assistant", "content": ai_message}
    )

    doc_meta = thread_document_metadata(thread_key)
    if doc_meta:
        st.caption(
            f"Document indexed: {doc_meta.get('filename')} "
            f"(chunks: {doc_meta.get('chunks')}, pages: {doc_meta.get('documents')})"
        )

st.divider()

if selected_thread:
    st.session_state["thread_id"] = selected_thread
    messages = load_conversation(selected_thread)

    temp_messages = []
    for msg in messages:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        temp_messages.append({"role": role, "content": msg.content})
    st.session_state["message_history"] = temp_messages
    st.session_state["ingested_docs"].setdefault(str(selected_thread), {})
    st.rerun()