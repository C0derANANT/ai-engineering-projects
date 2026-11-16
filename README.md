# 🤖 AI Engineering Projects

Hands-on generative AI applications I've built while learning AI engineering:
LLM APIs, prompt engineering, web scraping, streaming chat UIs and document generation.

| # | Project | What it does | Tech |
|---|---------|--------------|------|
| 01 | [AI Company Brochure Generator](01-Brochure-Generator) | Reads a company's website and writes a polished brochure, exported as styled PDF and DOCX | Gradio, Groq / Gemini, BeautifulSoup, fpdf2, python-docx |
| 02 | [AI Movie Chatbot](02-AI-Movie-Chatbot) | Chat app that answers anything about any movie: director, cast, budget, release, hit or flop | Gradio ChatInterface, Groq / Gemini, streaming |

## 🚀 Running a project

Each project has its own README. In general:

```bash
cd 01-Brochure-Generator          # or 02-AI-Movie-Chatbot
pip install -r requirements.txt
cp .env.example .env              # add your GROQ_API_KEY
python app.py                     # prints a local URL and a public share link
```

Get a free Groq API key at [console.groq.com/keys](https://console.groq.com/keys).

## 🧰 Skills used

- **LLMs:** OpenAI-compatible APIs (Groq, Gemini), system prompts, streaming, multi-turn chat memory
- **Python:** modular packages, dataclasses, type hints, logging, error handling
- **Web:** scraping with Requests + BeautifulSoup
- **UI:** Gradio Blocks and ChatInterface
- **Documents:** PDF (fpdf2) and Word (python-docx) generation

---

Built by **Anant Aggarwal** · B.Tech CSE (AI)
