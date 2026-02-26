from langchain.tools import tool
from database import get_news_summary
import tiktoken
import ollama
import chromadb
import re


@tool
def save_analysis_to_txt(content: str) -> str:
    """
    Saves the LLM's analysis to a text file.
    Provide the full analysis content as the 'content' argument.
    """
    filename = 'backend/Analyst_Team/report.txt'
    print("LLM is saving response to file")
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Analysis successfully saved to {filename}"
    except Exception as e:
        return f"Error saving file: {str(e)}"
    
@tool
def get_stock_analysis(symbol: str) -> str:
    """
    Retrieves summarized news-based stock analysis for a given ticker symbol.
    Input should be a valid stock ticker (e.g., AAPL, TSLA).
    """
    print("LLM getting info for individual stock")
    try:
        return get_news_summary(symbol=symbol)

    except Exception as e:
        return "no analysis for selected stock ticker"


tokenizer = tiktoken.get_encoding("cl100k_base")

def split_into_sentences(text):
    return re.split(r'(?<=[.!?]) +', text)

def chunk_sentences(sentences, max_tokens=400, overlap_tokens=100):
    chunks = []
    current_chunk = []
    current_tokens = 0

    for sentence in sentences:
        tokens = len(tokenizer.encode(sentence))

        if current_tokens + tokens > max_tokens:
            chunks.append(" ".join(current_chunk))

            # overlap
            overlap = []
            overlap_tokens_count = 0
            for s in reversed(current_chunk):
                t = len(tokenizer.encode(s))
                if overlap_tokens_count + t > overlap_tokens:
                    break
                overlap.insert(0, s)
                overlap_tokens_count += t

            current_chunk = overlap
            current_tokens = overlap_tokens_count

        current_chunk.append(sentence)
        current_tokens += tokens

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks



# needs to be improved in the future
@tool
def get_todays_headlines():
    """
    Retrieves and summarizes today's scraped news headlines
    using embeddings and vector similarity search.
    """
    print("LLM getting current news information")

    # first, get news summary from todays_headlines.txt

    file = open(f'backend/webscraping/todays_headlines.txt', 'r')
    contents = file.readlines()

    client = chromadb.Client()
    collection = client.create_collection(name='news')

    for i, article in enumerate(contents):
        sentences = split_into_sentences(article)
        chunks = chunk_sentences(sentences)

        for j, chunk in enumerate(chunks):
            response = ollama.embed(model="mxbai-embed-large", input=chunk)

            collection.add(ids=[f"{i}_{j}"], embeddings=response["embeddings"], documents=[chunk])

    query = "Summarize news with statistics"
    response = ollama.embed(model="mxbai-embed-large", input=query)


    results = collection.query(query_embeddings=response["embeddings"], n_results=8)

    
    context = " ".join(results["documents"][0]) if results["documents"] else ""

    return context



