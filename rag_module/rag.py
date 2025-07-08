"""
RAG (Retrieval-Augmented Generation) module for knowledge sources like codebase and Confluence pages.
"""

import os
from typing import List, Optional
import glob
from langchain_community.document_loaders import ConfluenceLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

class RAGKnowledgeBase:
    def __init__(self, sources: List[str], confluence_config: Optional[dict] = None):
        self.sources = sources
        self.code_chunks = []
        self.confluence_chunks = []
        self.confluence_config = confluence_config
        self._ingest_sources()
        if self.confluence_config:
            self._ingest_confluence()

    def _ingest_sources(self):
        """
        Ingests C code files from the provided sources (directories or files).
        Splits code into chunks for retrieval.
        """
        for source in self.sources:
            if os.path.isdir(source):
                c_files = glob.glob(os.path.join(source, '**', '*.c'), recursive=True)
                h_files = glob.glob(os.path.join(source, '**', '*.h'), recursive=True)
                files = c_files + h_files
            elif os.path.isfile(source) and (source.endswith('.c') or source.endswith('.h')):
                files = [source]
            else:
                continue
            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        code = f.read()
                        # Simple chunking: split by 40 lines per chunk
                        lines = code.splitlines()
                        for i in range(0, len(lines), 40):
                            chunk = '\n'.join(lines[i:i+40])
                            self.code_chunks.append({
                                'file': file_path,
                                'start_line': i+1,
                                'end_line': min(i+40, len(lines)),
                                'content': chunk
                            })
                except Exception as e:
                    # Could log or print error if needed
                    pass

    def _ingest_confluence(self):
        """
        Ingests Confluence pages using langchain_community's ConfluenceLoader and splits them into chunks.
        Expects self.confluence_config to be a dict with keys: url, username, api_token, space_key, (optional) page_ids or cql.
        """
        config = self.confluence_config
        if not config:
            return
        try:
            loader = ConfluenceLoader(
                url=config['url'],
                username=config['username'],
                api_token=config['api_token'],
                space_key=config.get('space_key'),
                page_ids=config.get('page_ids'),
                cql=config.get('cql')
            )
            docs = loader.load()
            splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=200)
            for doc in docs:
                for chunk in splitter.split_text(doc.page_content):
                    self.confluence_chunks.append({
                        'title': doc.metadata.get('title', 'Untitled'),
                        'url': doc.metadata.get('url', ''),
                        'content': chunk
                    })
        except Exception as e:
            # Could log or print error if needed
            pass

    def query(self, question: str, depth: str = "standard") -> str:
        """
        Retrieve the most relevant code and Confluence chunks for the question using simple keyword matching.
        Supports different search levels: quick, standard, deep.
        Returns a formatted string with the top relevant code and Confluence snippets.
        """
        if not question.strip():
            return "No question provided."

        import re
        question_words = set(re.findall(r'\w+', question.lower()))

        # Set retrieval parameters based on depth
        if depth == "deep":
            code_top_n = 8
            conf_top_n = 5
        elif depth == "quick":
            code_top_n = 1
            conf_top_n = 1
        else:  # standard
            code_top_n = 3
            conf_top_n = 2

        # Code chunk retrieval
        scored_code = []
        for chunk in self.code_chunks:
            chunk_text = chunk['content'].lower()
            score = sum(1 for word in question_words if word in chunk_text)
            if score > 0:
                scored_code.append((score, chunk))
        scored_code.sort(key=lambda x: (-x[0], x[1]['file']))
        top_code = scored_code[:code_top_n]

        # Confluence chunk retrieval
        scored_conf = []
        for chunk in self.confluence_chunks:
            chunk_text = chunk['content'].lower()
            score = sum(1 for word in question_words if word in chunk_text)
            if score > 0:
                scored_conf.append((score, chunk))
        scored_conf.sort(key=lambda x: (-x[0], x[1]['title']))
        top_conf = scored_conf[:conf_top_n]

        result = [f"Top relevant results for: {question}\n(Search level: {depth})\n"]
        references = []
        if top_code:
            result.append("Codebase matches:")
            for idx, (score, chunk) in enumerate(top_code, 1):
                result.append(f"[{idx}] {chunk['file']} (lines {chunk['start_line']}-{chunk['end_line']}):\n{chunk['content']}\n{'-'*40}")
                references.append(f"{chunk['file']} (lines {chunk['start_line']}-{chunk['end_line']})")
        if top_conf:
            result.append("Confluence matches:")
            for idx, (score, chunk) in enumerate(top_conf, 1):
                result.append(f"[{idx}] {chunk['title']} ({chunk['url']}):\n{chunk['content']}\n{'-'*40}")
                references.append(f"{chunk['title']} ({chunk['url']})")
        if not top_code and not top_conf:
            result.append(f"No relevant code or Confluence content found.\nIndexed {len(self.code_chunks)} code chunks, {len(self.confluence_chunks)} Confluence chunks.")
        else:
            result.append("\nReferences used:")
            for ref in references:
                result.append(f"- {ref}")
        return '\n'.join(result)
