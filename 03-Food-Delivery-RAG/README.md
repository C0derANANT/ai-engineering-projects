# 🍛 Food Delivery RAG

A RAG (Retrieval-Augmented Generation) application for a food delivery company like Zomato, built for the Incapp AI Engineer project. It answers customer and employee questions from the company's own documents: FAQs, ordering, refunds, support procedures and HR policies.

> **Status:** step 1 of 3. The knowledge base is ready. The vector database (RAG_DB) and the API and app come next.

## The knowledge base

The company, **CraveCart**, is fictional. Its knowledge base has 18 Markdown files (about 28,500 words) in [`knowledge-base/`](knowledge-base). Each subfolder becomes the `doc_type` metadata when the files are loaded.

| Folder (`doc_type`) | Files | What's covered |
|---|---|---|
| `company` | 2 | Company overview, cities, history; every fee on the bill; CraveCart Plus membership |
| `customer-faqs` | 3 | Orders and delivery; payments, refunds and offers; account, app and general |
| `ordering` | 5 | Placing, modifying and cancelling orders; delivery times and ETAs; live tracking |
| `policies` | 2 | Refund policy and cancellation policy, with worked examples |
| `support` | 2 | Customer support procedures (SLAs, refund limits, scenarios); technical support (error codes, incidents) |
| `hr-policies` | 4 | Leave, code of conduct, onboarding, benefits |

The documents share one set of facts (fees, time windows, refund rules), so the RAG never gets conflicting answers from different files. They include worked examples and edge cases, so retrieval quality can be tested on hard questions.

`knowledge-base.zip` contains the same folder, ready to upload to Google Drive for Colab.

## Using it with the RAG_DB notebook

The class `RAG_DB.ipynb` loads `knowledge-base/<folder>/*.md`, splits the text into 1000-character chunks with 200 overlap, embeds them with `all-MiniLM-L6-v2`, and stores them in Chroma. At those settings, this knowledge base makes about 210 chunks.

1. Upload `knowledge-base.zip` to Google Drive and unzip it into `MyDrive/ai/` so the path is `MyDrive/ai/knowledge-base/`.
2. Run `RAG_DB.ipynb`. No code changes are needed.

Keep only folders directly inside `knowledge-base/`. A loose file at that level breaks the folder loop in the notebook.

## Questions to test retrieval with

- "How much is the cancellation fee if the restaurant has already accepted my order?"
- "My Mutton Korma was missing and I used a coupon. How much refund do I get?"
- "What does error CC-PAY-302 mean?"
- "How many days of earned leave do I get, and can I carry them forward?"
- "Are delivery partners covered by employee health insurance?"
