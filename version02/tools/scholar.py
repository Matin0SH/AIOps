"""
REFACTORED: Simple LangChain-based RAG tool for network configuration search.

This implementation uses:
- LangChain FAISS integration for vector search
- Pure function-based design (no LangGraph state management)
- @tool decorator for agent integration
- Simple retrieve → rerank flow
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

from dotenv import load_dotenv
import google.generativeai as genai

# LangChain imports
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.documents import Document
from langchain_core.tools import tool

# Local imports
from .prompts import RERANK_PROMPT


# Configuration
CONFIG_DIR = Path(__file__).parent / "configs"
ENV_PATH = CONFIG_DIR / ".env"
DEFAULT_INDEX_DIR = Path(__file__).parent / "cfg_vdb"
EMBED_MODEL = "models/text-embedding-004"
GEN_MODEL = "gemini-2.0-flash-exp"

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# INITIALIZATION
# ============================================================================

def init_environment() -> None:
    """Load environment variables."""
    load_dotenv(ENV_PATH)
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not set in configs/.env")
    genai.configure(api_key=api_key)


def load_vector_store(index_dir: Path = DEFAULT_INDEX_DIR) -> FAISS:
    """
    Load FAISS vector store using LangChain.

    Best Practice:
    - Use LangChain's FAISS wrapper for consistency
    - Supports metadata filtering and async operations
    """
    init_environment()
    embeddings = GoogleGenerativeAIEmbeddings(
        model=EMBED_MODEL,
        task_type="retrieval_document"
    )

    try:
        vector_store = FAISS.load_local(
            str(index_dir),
            embeddings,
            allow_dangerous_deserialization=True  # Required for pickle
        )
        logger.info(f"Loaded FAISS index from {index_dir}")
        return vector_store
    except Exception as e:
        logger.error(f"Failed to load FAISS index: {e}")
        raise


# ============================================================================
# RETRIEVAL
# ============================================================================

def retrieve_documents(query: str, k: int = 5) -> List[Document]:
    """
    Retrieve top-k documents from FAISS.

    Args:
        query: Search query
        k: Number of documents to retrieve

    Returns:
        List of Document objects with page_content and metadata
    """
    try:
        vector_store = load_vector_store()
        retriever = vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": k}
        )
        docs = retriever.invoke(query)
        logger.info(f"Retrieved {len(docs)} documents for query: {query}")
        return docs
    except Exception as e:
        logger.error(f"Retrieval error: {e}", exc_info=True)
        return []


# ============================================================================
# RERANKING
# ============================================================================

def rerank_documents(
    query: str,
    documents: List[Document],
    top_n: int = 3,
    rerank_threshold: Optional[float] = None
) -> List[Document]:
    """
    Rerank documents using LLM with structured output.

    Best Practices:
    - Use ChatPromptTemplate for structured prompts
    - JsonOutputParser for reliable JSON extraction
    - Fallback to original order on parse failure

    Args:
        query: Original search query
        documents: List of retrieved documents
        top_n: Number of top documents to return after reranking

    Returns:
        List of top_n reranked Document objects with rerank scores in metadata
    """
    if not documents:
        logger.warning("No documents to rerank")
        return []

    try:
        init_environment()
        llm = ChatGoogleGenerativeAI(
            model=GEN_MODEL,
            temperature=0,
            convert_system_message_to_human=True
        )

        # Build prompt
        docs_text = "\n\n".join([
            f"doc_id: {i+1}\nmetadata: {json.dumps(doc.metadata, sort_keys=True)}\ncontent: {doc.page_content[:500]}"
            for i, doc in enumerate(documents)
        ])

        # Create chain with output parser
        parser = JsonOutputParser()
        chain = RERANK_PROMPT | llm | parser

        # Invoke reranking
        result = chain.invoke({"query": query, "documents": docs_text})
        evaluated = result.get("evaluated_documents", [])

        # Sort documents by score
        scored_docs = []
        for item in evaluated:
            doc_id = item.get("doc_id", 0)
            score = item.get("total_score", 0)
            if 1 <= doc_id <= len(documents):
                doc = documents[doc_id - 1]
                doc.metadata["rerank_score"] = score
                doc.metadata["rerank_reasoning"] = item.get("brief_reasoning", "")
                scored_docs.append((score, doc))

        # Sort by score descending
        scored_docs.sort(key=lambda x: x[0], reverse=True)

        # Optional post-rerank threshold (0-10 scale)
        if rerank_threshold is not None:
            scored_docs = [item for item in scored_docs if item[0] >= rerank_threshold]

        reranked = [doc for score, doc in scored_docs[:top_n]]

        logger.info(f"Reranked {len(documents)} docs to top {len(reranked)}")
        return reranked

    except Exception as e:
        logger.warning(f"Reranking failed, returning top {top_n} from original order: {e}")
        return documents[:top_n]


# ============================================================================
# TOOL DEFINITION (AGENT-READY)
# ============================================================================

@tool
def scholar_search(
    query: str,
    k: int = 5,
    top_n: int = 3,
    rerank_threshold: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Search network configuration notebooks using RAG (retrieve + rerank).

    This tool searches a vector database of Cisco IOS configuration notebooks,
    retrieves the most relevant ones, and reranks them using an LLM for accuracy.

    Args:
        query: Natural language query about network configuration (e.g., "enable SSH on VTY lines")
        k: Number of documents to retrieve from vector store (default: 5)
        top_n: Number of top documents to return after reranking (default: 3)

    Returns:
        List of dictionaries with notebook information:
        [
            {
                "id": "cfg_vty_ssh_v2_only",
                "title": "Enable SSH v2 only on VTY lines",
                "rerank_score": 9,
                "reasoning": "Exact match for SSH configuration on VTY"
            },
            ...
        ]

    Examples:
        >>> scholar_search("create VLAN 10", k=5, top_n=3)
        >>> scholar_search("configure OSPF routing", k=10, top_n=5)
    """
    try:
        # Step 1: Retrieve documents
        docs = retrieve_documents(query, k)
        if not docs:
            logger.warning(f"No documents retrieved for query: {query}")
            return []

        # Step 2: Rerank documents
        reranked = rerank_documents(query, docs, top_n, rerank_threshold)

        # Step 3: Format output
        results = [
            {
                "id": doc.metadata.get("id"),
                "title": doc.metadata.get("title"),
                "risk": doc.metadata.get("risk"),
                "semantic_tags": doc.metadata.get("semantic_tags", []),
                "rerank_score": doc.metadata.get("rerank_score", 0),
                "reasoning": doc.metadata.get("rerank_reasoning", "")
            }
            for doc in reranked
        ]

        logger.info(f"Returning {len(results)} reranked documents for query: {query}")
        return results

    except Exception as e:
        logger.error(f"scholar_search failed: {e}", exc_info=True)
        return []


# ============================================================================
# LEGACY API (for backwards compatibility)
# ============================================================================

class ScholarRAG:
    """
    Legacy wrapper for backwards compatibility.

    New code should use the @tool decorated scholar_search() function directly.

    Usage:
        scholar = ScholarRAG()
        result = scholar.query("enable SSH", k=5, top_n=3)
    """

    def query(
        self,
        query: str,
        k: int = 5,
        top_n: int = 3,
        rerank_threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Execute RAG pipeline (retrieve + rerank).

        Args:
            query: User's configuration question
            k: Number of documents to retrieve
            top_n: Number of documents to rerank

        Returns:
            Dict with results and metadata:
            {
                "query": "enable SSH",
                "retrieved_count": 5,
                "reranked_count": 3,
                "results": [...],
                "error": None
            }
        """
        try:
            results = scholar_search.invoke({
                "query": query,
                "k": k,
                "top_n": top_n,
                "rerank_threshold": rerank_threshold
            })

            return {
                "query": query,
                "retrieved_count": k,
                "reranked_count": len(results),
                "results": results,
                "error": None
            }
        except Exception as e:
            logger.error(f"Query execution failed: {e}", exc_info=True)
            return {
                "query": query,
                "retrieved_count": 0,
                "reranked_count": 0,
                "results": [],
                "error": str(e)
            }
