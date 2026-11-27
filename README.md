# 🤖 AI Engineering Projects

Hands-on generative AI applications I've built while learning AI engineering:
LLM APIs, prompt engineering, web scraping, streaming chat UIs and document generation.

| # | Project | What it does | Tech |
|---|---------|--------------|------|
| 01 | [AI Company Brochure Generator](01-Brochure-Generator) · [live demo](https://ai-brochure-generator-af0t.onrender.com) | Reads a company's website and writes a polished brochure in 11 languages, with your choice of sections, brand colour and logo, exported as styled PDF and DOCX. No invented contact details; Gemini takes over when Groq is busy | Gradio, Groq / Gemini, BeautifulSoup, fpdf2 + HarfBuzz, python-docx |
| 02 | [AI Movie](02-AI-Movie-Chatbot) | Movie chatbot that looks films up on Wikipedia with tool calls instead of answering from memory: director, cast and characters, budget, box office, plot, hit or flop, with source links. English, Hindi and Hinglish, typed or spoken | OpenAI SDK tool calling, Groq (gpt-oss, Qwen, Whisper), Gemini backup, Wikipedia API, Gradio |
| 03 | [Crave Assist: Food Delivery RAG](03-Food-Delivery-RAG) · [live demo](https://crave-assist.onrender.com) | RAG help assistant for a Zomato-style food delivery company. Answers from 18 policy and FAQ documents with citations, does exact refund and fee maths with tools, and speaks English, Hindi and Hinglish, with voice questions | LangChain, Chroma, BGE embeddings (ONNX), Groq (gpt-oss, Whisper), Gemini backup, Gradio |

Every project has tests that run on GitHub Actions and a Docker image deployed on Render's free plan (live demos take about a minute to wake after a quiet spell).

## 🚀 Running a project

Each project has its own README. In general:

```bash
cd 01-Brochure-Generator          # or 02-AI-Movie-Chatbot, 03-Food-Delivery-RAG
pip install -r requirements.txt
cp .env.example .env              # add your GROQ_API_KEY
python app.py                     # opens the app in your browser
```

Get a free Groq API key at [console.groq.com/keys](https://console.groq.com/keys).

## 🧰 Skills used

- **LLMs:** OpenAI-compatible APIs (Groq, Gemini), system prompts, streaming, multi-turn chat memory, tool calling, automatic fallback between models
- **RAG:** heading-aware chunking, Chroma vector search, query rewriting, citations
- **Python:** modular packages, dataclasses, type hints, logging, friendly error handling
- **Web:** scraping with Requests + BeautifulSoup, the Wikipedia API
- **UI:** Gradio Blocks and ChatInterface, voice input with Whisper
- **Documents:** PDF (fpdf2 + HarfBuzz) and Word (python-docx) generation
- **Shipping:** pytest, GitHub Actions, Docker, Render

---

Built by **Anant Aggarwal** · B.Tech CSE (AI)
