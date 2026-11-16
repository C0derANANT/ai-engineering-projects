# 🎬 AI Movie

A generative AI **chat application** for the Incapp AI Engineer assignment.
Ask anything about a movie and it answers: director, hero / cast, characters,
production house, budget, release date, and verdict (flop / hit / super hit).

## Tech used
- **openai**: OpenAI-compatible client, connected to **Groq** (`openai/gpt-oss-120b`), with **Gemini** (`gemini-3.6-flash`) as fallback
- **gradio**: `ChatInterface` with streaming replies and chat memory
- **python-dotenv**: loads API keys from `.env`

## Run
```bash
pip install -r requirements.txt
cp .env.example .env   # then paste your GROQ_API_KEY
python app.py   # prints a local URL and a public gradio.live link
```
Or open `AI-Movie-Chatbot.ipynb` and run all cells.
