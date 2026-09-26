FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ENABLECORS=false \
    STREAMLIT_SERVER_ENABLEXsrfProtection=true

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY langraph_rag_backend.py streamlit_rag_frontend.py run_chatbot.sh ./
COPY .streamlit ./.streamlit

RUN chmod +x run_chatbot.sh

EXPOSE 8080
CMD exec streamlit run streamlit_rag_frontend.py \
    --server.address=0.0.0.0 \
    --server.port=${PORT:-8080} \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=true
