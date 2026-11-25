---
title: Crave Assist
emoji: 🍛
colorFrom: yellow
colorTo: red
sdk: gradio
sdk_version: 6.20.0
python_version: "3.12"
app_file: app.py
pinned: false
short_description: RAG help assistant for a food delivery company
---

# 🍛 Crave Assist

A RAG help assistant for **CraveCart**, a fictional Zomato-style food delivery company.

- Answers from 18 policy and FAQ documents, with **citations** to the exact section used
- **Exact refund and cancellation maths** through tool calling, on 11 demo orders (#1042–#1052)
- Follow-up questions, **English, हिंदी and Hinglish**, and **voice questions** (Whisper)
- Groq `gpt-oss-120b`, with Gemini as an automatic backup

Source code and documentation: [github.com/C0derANANT/ai-engineering-projects](https://github.com/C0derANANT/ai-engineering-projects/tree/main/03-Food-Delivery-RAG)

**Space owner:** add `GROQ_API_KEY` (and optionally `GOOGLE_API_KEY`) under *Settings → Variables and secrets*.
