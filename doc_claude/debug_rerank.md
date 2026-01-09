# Debug: Why Rerank Returns Only 1 Document

## The Problem

When you run:
```python
result = scholar.query("create VLAN 10", k=5, top_n=3, enable_answer=False)
```

Log shows:
```
INFO:tools.scholar:Reranked 5 docs to top 1  # ← Should be "top 3"!
```

## Root Cause

The LLM reranker (Gemini) is **only evaluating/returning 1 document** in its JSON response instead of all 5.

## Where It Happens

**File:** scholar.py, line 184-200

```python
result = chain.invoke({"query": query, "documents": docs_text})
evaluated = result.get("evaluated_documents", [])  # ← LLM returns only 1 doc here

# Then we try to get top_n, but if LLM only gave us 1, we can only get 1
reranked = [doc for score, doc in scored_docs[:top_n]]  # top_n=3, but only 1 available
```

## Why LLM Returns Only 1 Document

The rerank prompt asks LLM to evaluate documents, but Gemini might be:
1. Only returning the **best** document
2. Ignoring lower-scored documents
3. Interpreting the prompt as "return the most relevant one"

## The Fix

**Option 1: Force LLM to return all documents**

Update the RERANK_PROMPT in prompts.py to explicitly state:

```python
RERANK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert relevance evaluator.

CRITICAL: You MUST evaluate and return ALL documents provided, not just the best ones.

Score documents 0-10 based on relevance.

OUTPUT FORMAT (JSON):
{{
  "evaluated_documents": [
    {{"doc_id": 1, "brief_reasoning": "...", "total_score": 8}},
    {{"doc_id": 2, "brief_reasoning": "...", "total_score": 6}},
    {{"doc_id": 3, "brief_reasoning": "...", "total_score": 5}},
    {{"doc_id": 4, "brief_reasoning": "...", "total_score": 3}},
    {{"doc_id": 5, "brief_reasoning": "...", "total_score": 2}}
  ]
}}

YOU MUST INCLUDE ALL {num_docs} DOCUMENTS IN YOUR RESPONSE.
"""),
    ("human", """Query: {query}

Documents:
{documents}

Evaluate ALL documents and return JSON with ALL {num_docs} entries:""")
])
```

**Option 2: Skip reranking if it fails**

In scholar.py, add fallback logic:

```python
def rerank_with_llm(query: str, documents: List[Document], llm, top_n: int = 5):
    # ... existing code ...

    try:
        result = chain.invoke({"query": query, "documents": docs_text})
        evaluated = result.get("evaluated_documents", [])

        # ← ADD THIS CHECK
        if len(evaluated) < len(documents):
            logger.warning(f"LLM only returned {len(evaluated)}/{len(documents)} docs, using original order")
            # Score all documents with default scores
            for i, doc in enumerate(documents):
                if i < len(evaluated):
                    # Use LLM score for docs it evaluated
                    pass
                else:
                    # Assign decreasing scores for unevaluated docs
                    doc.metadata["rerank_score"] = 5 - i
                    doc.metadata["rerank_reasoning"] = "Not evaluated by LLM"
            return documents[:top_n]

        # ... rest of existing code ...
```

## Immediate Workaround

Until we fix the prompt, you can:

1. **Use `enable_rerank=False`** to skip reranking:
```python
result = scholar.query(
    "create VLAN 10",
    k=5,
    top_n=3,  # This will work on retrieved_docs
    enable_rerank=False,
    enable_answer=False,
    return_documents=True
)
# Now you'll get 5 retrieved docs (not filtered to 3 though)
```

2. **Manually slice the docs**:
```python
result = scholar.query("create VLAN 10", k=5, enable_rerank=False, enable_answer=False, return_documents=True)
top_3_docs = result["retrieved_docs"][:3]
```

## Which Fix Do You Want?

1. Update the RERANK_PROMPT to force LLM to return all docs?
2. Add fallback logic to handle when LLM doesn't return all docs?
3. Both?

Let me know and I'll implement it!
