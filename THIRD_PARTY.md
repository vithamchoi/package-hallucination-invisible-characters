# Third-party code and data, not redistributed here

The experiments depend on the following. We link them rather than bundle them,
so that their own licences and versions govern.

| Component | Where | Used for |
|---|---|---|
| Groq API | groq.com | the inference endpoint |
| `openai/gpt-oss-20b` | served by Groq | the model whose answers were mined for package names |
| The Python Package Index | pypi.org | the registry queried for each extracted name |

Record the version or commit of each before re-running; the scripts do not pin them.
