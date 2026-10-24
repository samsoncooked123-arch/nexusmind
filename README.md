NexusMind
AI Knowledge Graph Explorer — turn scattered documents into connected, searchable knowledge.
Status: Early development. This README describes the planned product and architecture; features should not be considered implemented until available in the repository.

Overview
NexusMind is a hackathon project for exploring how ideas, entities, and relationships connect across research papers and text documents. Users will be able to upload documents, ask questions with an AI Knowledge Assistant, and inspect source evidence and graph paths behind answers.
Planned features
- PDF and text ingestion with document and page metadata
- Entity and relationship extraction with supporting source passages
- Interactive, clickable knowledge graph
- Topic discovery and community grouping
- Conversational question answering
- Hybrid retrieval using vector search and graph traversal
- Evidence Path Explorer that highlights relevant nodes, edges, and passages
- Clear handling of questions that cannot be answered from the uploaded sources
Planned technology stack
Layer	Technology	Purpose
Frontend	React + TypeScript + Vite	Web UI and chat interface
Graph UI	React Flow (@xyflow/react)	Interactive graph and highlighted paths
Backend	Python + FastAPI	APIs and application orchestration
PDF extraction	PyMuPDF	Extract text and page numbers
Language model	Ollama with a suitable model, or an approved hosted model	Extract entities and generate answers
Embeddings	Sentence Transformers	Embed passages and questions
Vector database	ChromaDB	Semantic passage retrieval
Graph database	Neo4j	Entities, relationships, and provenance
Metadata	SQLite	Document status and processing metadata
Graph algorithms	NetworkX	Graph analysis and topic/community detection


The exact model and dependency versions will be selected after compatibility and performance testing.
Intended workflow
1. Upload PDF or text documents.
2. Extract and chunk the text while preserving source metadata.
3. Extract entities and relationships and associate each relationship with a supporting passage.
4. Store graph data in Neo4j and text embeddings in ChromaDB.
5. Route questions to topic summaries, semantic search, graph traversal, or a combination.
6. Generate answers from retrieved evidence.
7. Display the answer, citations, and relevant graph path in the frontend.
Architecture
React + TypeScript + React Flow
              |
              v
            FastAPI
              |
              v
      AI Knowledge Assistant
        /                \\
Vector retrieval       Graph retrieval
        |                |
     ChromaDB           Neo4j
        \\                /
         Retrieved evidence
                 |
                 v
       Answer + citations
       + highlighted path
Getting started
The application is still being scaffolded. Setup commands will be added once the initial frontend and backend are committed.
Planned prerequisites
- Python 3.11+ (subject to dependency compatibility)
- Node.js and npm
- Neo4j, local or hosted
- Ollama or an approved LLM endpoint, depending on the selected model
Configuration and security
- Keep credentials in local environment variables.
- Commit only a sanitized .env.example, never API keys or passwords.
- Use public or synthetic documents for demos unless you have permission to process other material.
Roadmap
- [ ] Scaffold React + TypeScript frontend and FastAPI backend
- [ ] Implement PDF upload, extraction, chunking, and page references
- [ ] Add entity and relationship extraction with evidence
- [ ] Connect Neo4j and ChromaDB
- [ ] Implement query routing and evidence-grounded answers
- [ ] Visualize the graph and highlight relevant paths
- [ ] Add topic clustering and basic entity deduplication
- [ ] Test unsupported questions and relationship accuracy
- [ ] Write setup instructions and prepare an end-to-end demo
Team workflow
Create focused issues for ingestion, graph storage, retrieval, frontend, and integration. Agree on API response formats before building frontend and backend independently. Keep changes small and test the complete upload-to-answer workflow frequently.
Goal
NexusMind aims to make document collections easier to explore by connecting concepts across sources and showing what supports each answer and relationship.
