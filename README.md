# AI Automated Code Reviewer

A simple AI-powered code review web application built with Python, Streamlit, and the Groq API. Paste source code, pick a programming language, and receive a structured review covering bugs, security issues, performance improvements, best practices, and suggested improved code.

## Features

- Clean Streamlit UI with responsive layout
- Language selector for multi-language reviews
- AI-powered reviews with structured markdown output
- Bug, security, performance, quality, and best-practice analysis
- Severity guidance and review score out of 10
- Copy-to-clipboard button for the generated review
- Downloadable markdown report
- Syntax-highlighted code preview
- Empty input validation and error handling
- Review history in the current session

## Project Structure

```text
automated_code_reviewer/
├── app.py
├── reviewer.py
├── requirements.txt
├── .env
├── README.md
└── utils/
    └── prompts.py
```

## Prerequisites

- Python 3.10 or newer
- A Groq API key
- A virtual environment is recommended

## Environment Setup

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama3-70b-8192
```

You can use the provided `.env` file as a template, but do not commit real secrets.

## Installation

1. Clone or open the project folder.
2. Create and activate a virtual environment.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Running Locally

Start the Streamlit app:

```bash
streamlit run app.py
```

Then open the local URL shown in the terminal.

## How It Works

1. Select a programming language.
2. Paste source code into the editor.
3. Click **Review Code**.
4. The app sends the code to the Groq API.
5. The model returns a structured markdown review.

## Prompt Format

The assistant is instructed to return these sections:

- Summary
- Bugs
- Security Issues
- Performance Improvements
- Best Practices
- Suggested Improved Code

## Deployment on Streamlit Cloud

1. Push the project to a GitHub repository.
2. Go to Streamlit Community Cloud and create a new app.
3. Select the repository, branch, and `app.py` as the main file.
4. Add `GROQ_API_KEY` in the app settings or Streamlit secrets.
5. Ensure `requirements.txt` is present in the repo.
6. Deploy and verify that the app can reach the Groq API.

If you prefer secrets over environment files on Streamlit Cloud, add a `.streamlit/secrets.toml` entry such as:

```toml
GROQ_API_KEY = "your_groq_api_key"
GROQ_MODEL = "llama3-70b-8192"
```

## Notes

- The app is designed to analyze code quality and security concerns, but it should not replace human review.
- Keep API keys out of source control.
- For production use, consider adding authentication, rate limiting, and logging.
