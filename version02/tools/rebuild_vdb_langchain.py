"""
Rebuild FAISS vector database using LangChain format.

This script converts notebooks.json into a LangChain-compatible FAISS index
with proper pickle metadata format.
"""
import json
from pathlib import Path
from dotenv import load_dotenv

from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document


def load_notebooks(notebooks_path: Path) -> list:
    """Load notebooks from JSON file."""
    with notebooks_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("notebooks", [])


def notebook_to_document(notebook: dict) -> Document:
    """
    Convert notebook dict to LangChain Document.

    Document has:
    - page_content: searchable text
    - metadata: structured data
    """
    # Build searchable content
    tags = ", ".join(notebook.get("semantic_tags", []))
    scope = ", ".join(notebook.get("device_scope", []))
    commands = "\n".join(notebook.get("config_commands", []))

    page_content = f"""
id: {notebook.get('id', '')}
title: {notebook.get('title', '')}
description: {notebook.get('description', '')}
risk: {notebook.get('risk', '')}
device_scope: {scope}
semantic_tags: {tags}
config_commands:
{commands}
""".strip()

    # Build metadata (must be JSON-serializable)
    metadata = {
        "id": notebook.get("id"),
        "title": notebook.get("title"),
        "risk": notebook.get("risk"),
        "semantic_tags": notebook.get("semantic_tags", []),
        "device_scope": notebook.get("device_scope", []),
        "requires_approval": notebook.get("requires_approval", False),
    }

    return Document(page_content=page_content, metadata=metadata)


def rebuild_vector_store(
    notebooks_path: Path,
    output_dir: Path,
    embed_model: str = "models/text-embedding-004"
):
    """
    Rebuild FAISS vector store using LangChain.

    Creates:
    - index.faiss (vector index)
    - index.pkl (pickled metadata)
    """
    print(f"Loading notebooks from {notebooks_path}...")
    notebooks = load_notebooks(notebooks_path)
    print(f"Loaded {len(notebooks)} notebooks")

    print("Converting notebooks to LangChain Documents...")
    documents = [notebook_to_document(nb) for nb in notebooks]
    print(f"Created {len(documents)} documents")

    print(f"Initializing embeddings model: {embed_model}...")
    embeddings = GoogleGenerativeAIEmbeddings(
        model=embed_model,
        task_type="retrieval_document"
    )

    print("Building FAISS index (this may take a minute)...")
    vector_store = FAISS.from_documents(documents, embeddings)
    print("FAISS index built successfully")

    print(f"Saving to {output_dir}...")
    output_dir.mkdir(parents=True, exist_ok=True)
    vector_store.save_local(str(output_dir))

    print(f"\n✅ Success! Vector store saved to {output_dir}")
    print(f"   - {output_dir}/index.faiss (vector index)")
    print(f"   - {output_dir}/index.pkl (metadata)")

    return vector_store


def main():
    """Main entry point."""
    # Load environment
    config_dir = Path(__file__).parent / "configs"
    env_path = config_dir / ".env"
    load_dotenv(env_path)

    # Paths
    notebooks_path = Path(__file__).parent / "notebooks.json"
    output_dir = Path(__file__).parent / "cfg_vdb"

    print("=" * 80)
    print("REBUILDING FAISS VECTOR STORE WITH LANGCHAIN")
    print("=" * 80)

    # Rebuild
    rebuild_vector_store(
        notebooks_path=notebooks_path,
        output_dir=output_dir,
        embed_model="models/text-embedding-004"
    )

    print("\n" + "=" * 80)
    print("You can now use scholar.py!")
    print("=" * 80)


if __name__ == "__main__":
    main()
