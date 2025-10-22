from .state import QUESTIONS, NN_MODEL, EMBEDDER, TOP_K


def build_index_from_memory():
    global NN_MODEL
    if not QUESTIONS:
        return
    embeddings = EMBEDDER.encode(QUESTIONS, show_progress_bar=False)
    NN_MODEL = NN_MODEL.__class__(n_neighbors=min(len(QUESTIONS), TOP_K), metric="cosine")
    NN_MODEL.fit(embeddings)
