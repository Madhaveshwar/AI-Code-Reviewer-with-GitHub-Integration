# AI Code Reviewer with GitHub Integration

An advanced AI-powered code review assistant that automates pull request analysis, vulnerability scanning, code quality reviews, test generation, and repository health scoring.

---

## 🚀 Resume Profile Ready

### **Project Title:**
AI Code Reviewer with GitHub Integration

### **Description:**
Created an AI-powered code review assistant integrated with GitHub for automated pull request analysis, security vulnerability detection, code smell identification, test case generation, inline review comments, severity scoring, and repository health analysis using the Groq API, Streamlit, PyGithub, and LangSmith.

---

## 🌟 Key Features

1. **GitHub Repository Integration**
   - Seamlessly connect to public or private repositories via GitHub Personal Access Tokens (PAT).
   - Display real-time metadata including Stars, Forks, Open PRs, and language metrics.

2. **Automated Pull Request Reviews**
   - Fetch and select from list of open pull requests.
   - Extract changed files and diff patches to target review assessments only on modified lines.
   - Show PR statistics (Author, Title, Added/Deleted lines, Files Changed).

3. **Advanced AI Multi-Scanner Engine**
   - Orchestrated using the Groq API (`llama-3.3-70b-versatile`).
   - Runs concurrent review pipelines: Logic & Bugs, Security Audits, and Code Smells.
   - Classifies findings dynamically using severity levels: *Critical, High, Medium, Low, Info*.

4. **Code Smell & Anti-Pattern Detection**
   - Scans for long functions, duplicate/dead code, nesting, naming violations, and magic numbers.

5. **Deep Security Auditing**
   - Spot vulnerability patterns: SQL Injection, XSS, Command Injection, hardcoded secrets, weak auth, and insecure deserialization.

6. **Automated Test Suggestions**
   - Generates boilerplate code and blueprints for Unit Tests, Integration Tests, Edge Cases, and Negative Tests.

7. **Interactive Comment Posting & Inline Comments**
   - Generate standard inline review format comments.
   - Post overall PR summary reviews to GitHub discussion timelines.
   - Post inline comments directly to the specific file lines inside GitHub's PR file diff view.

8. **Repository Structure & Health Scoring**
   - Traversing Git trees recursively to calculate a Repository Health Score out of 100.
   - Flags missing documentation (README), large files (>500KB), vulnerable dependencies, and un-tested security hotspots.

9. **Premium PDF, Markdown, & JSON Export**
   - Generates beautifully styled PDF reports using `fpdf2` with a robust text encoder to prevent Unicode errors.
   - Export structured raw findings in JSON or formatted Markdown documentation.

10. **LangSmith Trace Integrations**
    - Traces operational logic (Prompt, Repository, PR Number, AI Review Result, Latency, and estimated tokens) using LangSmith's `@traceable` pipelines.

---

## 📁 Project Structure

Refactored layout:

```text
ai_code_reviewer/
│
├── app.py                   # Main Streamlit dashboard application UI
├── github_service.py        # PyGithub wrapper for repo stats, PR details, and comments
├── reviewer.py              # Orchestration manager coordinating all review engines
├── security_scanner.py      # Specialised AI Security scanner targeting vulnerabilities
├── code_smell_detector.py  # Code quality scanner identifying anti-patterns & smells
├── test_generator.py        # Test suggestion engine proposing QA cases
├── repository_analyzer.py   # Tree parser scoring repository health & documentation
├── report_generator.py      # PDF, Markdown, and JSON file generation suite
│
├── utils/
│   ├── __init__.py
│   ├── prompts.py           # Contains prompt templates for all analysis models
│   └── validation.py        # Heuristics checking if inputs are programming code
├── prompts/
├── templates/
├── exports/                 # Cache folder storing downloaded PDF reports
└── requirements.txt         # Subproject dependencies
```

---

## 🛠️ Prerequisites

- Python 3.10 to 3.12
- A Groq API Key
- A GitHub Personal Access Token (PAT) with `repo` scope (for PR integrations)
- A LangSmith API Key (Optional, for execution tracing)

---

## 🔧 Environment Setup

Create a `.env` file in the root workspace directory:

```env
# Groq API Key Setup
GROQ_API_KEY=your_groq_api_key

# GitHub Token (Optional default)
GITHUB_TOKEN=your_github_personal_access_token

# LangSmith Setup (Optional)
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=Automated_Code_Reviewer
```

---

## 🚀 Installation & Launch

1. Clone this repository or open the project folder.
2. Setup a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the Streamlit dashboard using the launcher:
   ```bash
   python run.py
   ```
   *Alternative:*
   ```bash
   streamlit run ai_code_reviewer/app.py
   ```

---

## 🛡️ License

This project is licensed under the MIT License.
