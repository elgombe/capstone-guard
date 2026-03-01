"""
similarity.py — Gemini-powered semantic duplicate detection.

Install:  pip install google-genai numpy python-dotenv
Add to .env:
    GEMINI_API_KEY=your-key-here
    SIMILARITY_THRESHOLD=0.82
    TITLE_SIMILARITY_WEIGHT=0.4
    DESCRIPTION_SIMILARITY_WEIGHT=0.6

Get a free API key at: https://aistudio.google.com/app/apikey
Free tier: 1,500 embedding requests/day — no credit card needed.
"""

import os
import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

_client = None

def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in your .env file.")
        _client = genai.Client(api_key=api_key)
    return _client


def get_embedding(text: str) -> np.ndarray:
    """
    Get a Gemini embedding vector for a piece of text.
    Uses gemini-embedding-001 (768-dimensional, semantically rich).
    """
    text = text.strip().replace('\n', ' ')
    result = _get_client().models.embed_content(
        model='gemini-embedding-001',
        contents=text,
        config=types.EmbedContentConfig(task_type='SEMANTIC_SIMILARITY')
    )
    return np.array(result.embeddings[0].values)


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Cosine similarity between two vectors. Returns 0.0–1.0."""
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Semantic similarity between two texts using Gemini embeddings.
    Returns a float between 0.0 and 1.0.
    """
    if not text1.strip() or not text2.strip():
        return 0.0
    try:
        return cosine_similarity(get_embedding(text1), get_embedding(text2))
    except Exception as e:
        print(f"[similarity] Gemini error: {e}")
        return 0.0


def find_similar_projects(title: str, description: str,
                           threshold: float = None,
                           exclude_id: int = None) -> list:
    """
    Find projects semantically similar to the given title + description.
    Catches paraphrased duplicates that SequenceMatcher misses.

    Returns list of dicts sorted by overall_similarity descending:
        [{
            'project': <Project ORM object>,
            'title_similarity': float,
            'description_similarity': float,
            'overall_similarity': float
        }]
    """
    from models.db import Project, ProjectStatus

    if threshold is None:
        threshold = float(os.environ.get('SIMILARITY_THRESHOLD', 0.82))

    title_weight = float(os.environ.get('TITLE_SIMILARITY_WEIGHT', 0.4))
    desc_weight  = float(os.environ.get('DESCRIPTION_SIMILARITY_WEIGHT', 0.6))

    # Embed the incoming project ONCE (2 API calls total)
    try:
        incoming_title_vec = get_embedding(title)
        incoming_desc_vec  = get_embedding(description)
    except Exception as e:
        print(f"[similarity] Could not embed incoming project: {e}")
        return []

    query = Project.query.filter_by(status=ProjectStatus.APPROVED)
    if exclude_id:
        query = query.filter(Project.id != exclude_id)
    all_projects = query.all()

    results = []
    for project in all_projects:
        try:
            title_sim = cosine_similarity(
                incoming_title_vec, get_embedding(project.title)
            )
            desc_sim = cosine_similarity(
                incoming_desc_vec, get_embedding(project.description)
            )
        except Exception as e:
            print(f"[similarity] Skipping project {project.id}: {e}")
            continue

        overall_sim = title_weight * title_sim + desc_weight * desc_sim

        if overall_sim >= threshold:
            results.append({
                'project':                project,
                'title_similarity':       round(title_sim, 4),
                'description_similarity': round(desc_sim, 4),
                'overall_similarity':     round(overall_sim, 4),
            })

    results.sort(key=lambda x: x['overall_similarity'], reverse=True)
    return results