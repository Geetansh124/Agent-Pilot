#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${project_dir}"
exec streamlit run streamlit_rag_frontend.py
