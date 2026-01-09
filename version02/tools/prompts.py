"""
Prompt templates for the RAG pipeline (retrieval + reranking).
All prompts use LangChain's ChatPromptTemplate for consistency.
"""
from langchain_core.prompts import ChatPromptTemplate


# ============================================================================
# RERANKING PROMPTS
# ============================================================================

RERANK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert relevance evaluator for network configuration notebooks.

Score each document 0-10 based on how well it matches the user's configuration intent.
Return JSON only. Do not include extra keys.

SCORING:
- 9-10: Excellent - Direct match, ready to execute
- 7-8: Very Good - Strong match with minor gaps
- 5-6: Good - Partial match
- 3-4: Fair - Tangentially related
- 0-2: Poor/Irrelevant

OUTPUT FORMAT (JSON only):
{{
  "evaluated_documents": [
    {{
      "doc_id": 1,
      "brief_reasoning": "One sentence explanation",
      "total_score": 8
    }}
  ]
}}"""),
    ("human", """Query: {query}

Documents (doc_id starts at 1):
{documents}

Evaluate every document listed and return JSON only.""")
])


# ============================================================================
# LEGACY PROMPTS (for backwards compatibility)
# ============================================================================

def build_reranker_prompt(query: str, documents_text: str) -> str:
    """
    Legacy function for backwards compatibility.
    Use RERANK_PROMPT.invoke() instead.
    """
    return RERANK_PROMPT.format(query=query, documents=documents_text)
