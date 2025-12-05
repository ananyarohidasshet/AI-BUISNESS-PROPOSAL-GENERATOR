# --------------------------------------------------------------
# app.py – OLLAMA + LLAMA 3.2 (LOCAL, NO GPU, NO TOKEN)
# --------------------------------------------------------------
import os
import time
import random
import json
import requests
from typing import Dict, List
from dataclasses import dataclass

import streamlit as st
import mlflow

# --------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
mlflow.set_tracking_uri(MLFLOW_URI)
mlflow.set_experiment("Business Proposal Generator")

SIMULATION_MODE = os.getenv("SIMULATION_MODE", "False").lower() == "true"
OLLAMA_URL = "http://localhost:11434/api/generate"  # Ollama default
OLLAMA_MODEL = "llama3.2"  # ← Your model name in Ollama

# --------------------------------------------------------------
# TEMPLATES
# --------------------------------------------------------------
@dataclass
class ProposalTemplate:
    id: str
    title: str
    structure: List[str]
    icon: str

class TemplateManager:
    @staticmethod
    def get_templates() -> List[ProposalTemplate]:
        return [
            ProposalTemplate(
                id="startup_seed",
                title="Startup Seed Funding",
                structure=[
                    "Executive Summary", "Problem Statement", "Solution",
                    "Market Opportunity", "Business Model", "Traction",
                    "Team", "Financials", "The Ask"
                ],
                icon="rocket"
            ),
            ProposalTemplate(
                id="strategic_partnership",
                title="Strategic Partnership",
                structure=[
                    "Introduction", "Shared Vision", "Synergies",
                    "Operating Model", "Financials", "Next Steps"
                ],
                icon="handshake"
            )
        ]

SECTION_PROMPTS = {
    "Executive Summary": "Write a 3-4 sentence executive summary. Company: {company_name}. Goal: {goal}. Tone: {tone}.",
    "Problem Statement": "Describe the core problem. Use urgency.",
    "Solution": "Explain how {company_name} solves it.",
    "Market Opportunity": "Estimate TAM and growth.",
    "Business Model": "List revenue streams.",
    "Traction": "Show users or revenue.",
    "Team": "Highlight key founders.",
    "Financials": "Project 3-year revenue.",
    "The Ask": "State funding and use of funds.",
    "Introduction": "Introduce both companies.",
    "Shared Vision": "Describe joint future.",
    "Synergies": "Detail cost/revenue upside.",
    "Operating Model": "Propose team and IP.",
    "Financials": "Model joint P&L.",
    "Next Steps": "Suggest NDA, diligence, term sheet."
}

# --------------------------------------------------------------
# LLM HANDLER – OLLAMA API
# --------------------------------------------------------------
class LLMHandler:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, model_name: str, simulate: bool = True):
        if hasattr(self, "initialized"): return
        self.model_name = model_name
        self.simulate = simulate
        self.initialized = True

    def generate_section(self, section_name: str, context: Dict, run_id: str | None = None) -> str:
        start = time.time()

        if self.simulate:
            time.sleep(random.uniform(0.8, 1.8))
            return f"**{section_name}**: Mock for {context.get('company_name')}."

        prompt = SECTION_PROMPTS.get(section_name, "Write {section_name}.").format(
            company_name=context.get('company_name', 'Company'),
            goal=context.get('goal', 'growth'),
            tone=context.get('tone', 'Professional').lower()
        )

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "max_tokens": 512
            }
        }

        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=120)
            response.raise_for_status()
            result = response.json().get("response", "").strip()
            latency = time.time() - start
            if run_id:
                mlflow.log_metric(f"latency_{section_name.lower().replace(' ', '_')}", latency)
            return result
        except Exception as e:
            return f"[Ollama Error: {e}]"

# --------------------------------------------------------------
# STREAMLIT UI
# --------------------------------------------------------------
st.set_page_config(page_title="OpenProp AI", page_icon="whale", layout="wide")

for key in ['step', 'form_data', 'generated_proposal', 'run_id', 'selected_template']:
    if key not in st.session_state:
        st.session_state[key] = 1 if key == 'step' else ({} if key == 'form_data' else "")

llm = LLMHandler(OLLAMA_MODEL, simulate=SIMULATION_MODE)
templates = TemplateManager.get_templates()

with st.sidebar:
    st.title("MLOps Dashboard")
    st.success("System Online")
    mode = "Simulation" if SIMULATION_MODE else f"Ollama ({OLLAMA_MODEL})"
    st.info(f"Mode: {mode}")
    st.markdown(f"[MLflow UI]({MLFLOW_URI})")
    if st.session_state.run_id:
        st.caption(f"Run ID: `{st.session_state.run_id[:8]}`")

# --- STEP 1 ---
if st.session_state.step == 1:
    st.header("Choose Template")
    cols = st.columns(2)
    for i, tmpl in enumerate(templates):
        with cols[i % 2]:
            if st.button(f"{tmpl.icon} **{tmpl.title}**", use_container_width=True):
                st.session_state.selected_template = tmpl
                st.session_state.step = 2
                st.rerun()

# --- STEP 2 ---
elif st.session_state.step == 2:
    tmpl = st.session_state.selected_template
    st.header("Enter Details")
    with st.form("input_form"):
        company = st.text_input("Company Name", "NexaAI")
        goal = st.text_area("Goal", "Raise $2M seed")
        tone = st.selectbox("Tone", ["Professional", "Bold", "Friendly"])
        submitted = st.form_submit_button("Generate", type="primary")

        if submitted and company.strip():
            st.session_state.form_data = {"company_name": company, "goal": goal, "tone": tone}
            with mlflow.start_run() as run:
                st.session_state.run_id = run.info.run_id
                full = f"# {tmpl.title}\n\n**Company**: {company}\n\n"
                prog = st.progress(0)
                for idx, sec in enumerate(tmpl.structure):
                    st.write(f"**{sec}**...")
                    content = llm.generate_section(sec, st.session_state.form_data, run.info.run_id)
                    full += f"## {sec}\n\n{content}\n\n"
                    prog.progress((idx + 1) / len(tmpl.structure))
                mlflow.log_text(full, "proposal.md")
            st.session_state.generated_proposal = full
            st.session_state.step = 3
            st.rerun()

# --- STEP 3 ---
elif st.session_state.step == 3:
    st.header("Generated Proposal")
    st.markdown(st.session_state.generated_proposal)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Start Over"):
            for k in ['step', 'form_data', 'generated_proposal', 'run_id', 'selected_template']:
                st.session_state.pop(k, None)
            st.rerun()
    with c2:
        st.download_button("Download", st.session_state.generated_proposal, "proposal.md", "text/markdown")
    if st.session_state.run_id:
        st.caption(f"MLflow Run ID: `{st.session_state.run_id}`")