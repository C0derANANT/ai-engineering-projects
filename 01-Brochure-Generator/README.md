# 🏢 AI Company Brochure Generator

Turn any company's website into a polished, ready-to-share brochure in seconds.
The app reads the company's website, uses an LLM to write the brochure, shows a
live preview, and exports it as a styled **PDF** and **Word (DOCX)** file.

Built as part of the Incapp AI Engineer course.

## ✨ Features

- **Website-aware:** scrapes the homepage plus key pages (About, Services, Careers) for real facts
- **Live streaming preview:** watch the brochure being written
- **Customisable:** tone (Professional, Friendly, Witty, Luxury), format (bullets / paragraphs / mixed), length and target audience
- **No made-up facts:** the prompt forbids inventing contact details, numbers or clients; it uses `[Phone]` style placeholders instead
- **Styled exports:** PDF with a title banner, section headings, real bullets and page numbers; DOCX with proper Word headings and lists
- **Multiple LLM providers:** Groq by default, Gemini as a fallback (both via the OpenAI-compatible API)

## 🧰 Tech Stack

| Purpose        | Library                    |
| -------------- | -------------------------- |
| Web UI         | Gradio                     |
| LLM client     | OpenAI SDK → Groq / Gemini |
| Web scraping   | Requests + BeautifulSoup   |
| PDF export     | fpdf2                      |
| Word export    | python-docx                |
| Config         | python-dotenv              |

## 📁 Project Structure

```
01-Brochure-Generator/
├── app.py                    # Gradio web app (entry point)
├── Brochure-Generator.ipynb  # Notebook: use the package or launch the app from Jupyter
├── brochure/
│   ├── config.py             # API keys, model and paths
│   ├── scraper.py            # Website scraping
│   ├── generator.py          # Prompt building + LLM streaming
│   └── exporters.py          # Markdown → PDF / DOCX
├── outputs/                  # Generated brochures (git-ignored)
├── legacy/                   # Original v1 notebook
├── requirements.txt
└── .env.example
```

## 🚀 Getting Started

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your API key
cp .env.example .env     # then paste your GROQ_API_KEY

# 3. Run
python app.py            # opens in your browser + prints a public link
```

> A `.env` in any parent folder also works, since the app searches upward for it.

## ⚙️ Configuration

| Variable         | Required | Default                 |
| ---------------- | -------- | ----------------------- |
| `GROQ_API_KEY`   | Yes*     | none                    |
| `GROQ_MODEL`     | No       | `openai/gpt-oss-120b`   |
| `GOOGLE_API_KEY` | Yes*     | none (used if no Groq key) |

\* At least one of the two keys is required.

## 📝 Changelog

**v2:** refactored the notebook into a modular app:
- Fixed PDF exports where every hyphen and bullet showed up as `?`
- Real formatting (bold, headings, bullet lists) in both PDF and DOCX
- Unique timestamped filenames instead of overwriting `brochure.pdf`
- Scrapes key sub-pages, accepts URLs without `https://`, warns on unreadable sites
- Public share link (`share=True`) printed on every run
- Streaming preview, tone/format/length options, input validation
