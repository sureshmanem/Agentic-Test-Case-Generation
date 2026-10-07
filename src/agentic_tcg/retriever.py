"""Knowledge base: markdown docs split by heading into an in-memory Chroma store.

The store is rebuilt on start, so it never goes stale. With six small documents
that costs one embeddings call.
"""

import uuid
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter

from agentic_tcg.config import get_settings
from agentic_tcg.models import load_knowledge_docs


@dataclass(frozen=True)
class Chunk:
    source: str
    section: str
    text: str

    def as_context(self) -> str:
        return f"[{self.source} > {self.section}]\n{self.text}"


def split_docs(docs: dict[str, str]) -> list[Document]:
    splitter = MarkdownHeaderTextSplitter([("#", "h1"), ("##", "h2")], strip_headers=False)
    chunks = []
    for name, text in docs.items():
        for doc in splitter.split_text(text):
            section = doc.metadata.get("h2") or doc.metadata.get("h1") or name
            chunks.append(Document(page_content=doc.page_content, metadata={"source": name, "section": section}))
    return chunks


def default_embeddings() -> Embeddings:
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=get_settings().embedding_model)


class KnowledgeBase:
    def __init__(self, embeddings: Embeddings | None = None, docs: dict[str, str] | None = None):
        client = chromadb.EphemeralClient(settings=ChromaSettings(anonymized_telemetry=False))
        self.store = Chroma(
            collection_name=f"knowledge-{uuid.uuid4().hex[:12]}",
            embedding_function=embeddings or default_embeddings(),
            client=client,
            collection_metadata={"hnsw:space": "cosine"},
        )
        self.documents = split_docs(docs if docs is not None else load_knowledge_docs())
        if self.documents:
            self.store.add_documents(self.documents)

    def search(self, queries: list[str], k: int | None = None, max_chunks: int = 8) -> list[Chunk]:
        """Run every query and keep the best-scoring unique chunks (lower distance = better)."""
        k = k or get_settings().retrieval_k
        best: dict[tuple[str, str, str], float] = {}
        for query in queries:
            for doc, distance in self.store.similarity_search_with_score(query, k=k):
                key = (doc.metadata["source"], doc.metadata["section"], doc.page_content)
                best[key] = min(distance, best.get(key, distance))
        ranked = sorted(best.items(), key=lambda item: item[1])[:max_chunks]
        return [Chunk(source=s, section=sec, text=t) for (s, sec, t), _ in ranked]
