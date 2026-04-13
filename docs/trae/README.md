# Trae Agent Workspace

Welcome to the Trae Agent workspace. This directory (`/docs/trae/`) serves as the planning, tracking, and knowledge base area for the **Trae AI Assistant** and its human partner. 

Our goal is to collaborate with the THE-Seed OpenRA development team by providing high-quality, modular, and non-intrusive enhancements to the project's AI capabilities.

## 🎯 Our Development Focus

As an AI-human pair programming team, our contributions are specifically focused on the following areas:

1. **State Abstraction & Data Analytics (`openra_state`)**
   - Processing raw telemetry data from the OpenRA engine into high-level, semantic tactical data.
   - Implementing combat scoring, unit evaluations, and spatial clustering (e.g., DBSCAN) to structurally understand the battlefield.

2. **Information Experts (Heuristic Modules)**
   - Designing independent, non-intrusive evaluation modules (e.g., `DisadvantageAssessor`).
   - Generating high-level tactical signals (e.g., Global Disadvantage, Local Squad Disadvantage, Economic Shortage) without forcefully altering the existing Finite State Machines (`combat.py`, `economy.py`).

3. **LLM Integration Preparation**
   - Structuring battlefield data into clear, concise formats suitable for LLM context windows.
   - Building the bridge between heuristic evaluations and LLM command generation.

## 🛠️ Contribution Philosophy

- **Zero Intrusion**: We prioritize creating standalone modules with clear input/output interfaces. We provide READMEs and documentation for downstream integration, leaving the final architectural decisions to the core maintainers.
- **Data-Driven**: We prefer mathematical and algorithmic evaluations (e.g., combat power scoring, clustering) over simple unit counting.

## 📁 Workspace Structure

- `agents.md`: Internal knowledge base and conventions for the Trae Agent.
- `plan.md`: Current task states and roadmap.
- `progress.md`: Changelog and progress tracking of our tasks.
- `README.md`: This document, explaining our role and focus to the upstream maintainers.

---
*We look forward to contributing to the THE-Seed OpenRA project!*
