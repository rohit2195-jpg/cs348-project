

from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
import os
from dotenv import load_dotenv
from llm_model import model

load_dotenv()
'''
tokenizer = tiktoken.get_encoding("cl100k_base")


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



def test():
    response = chat(model='deepseek-r1:1.5b', messages=[
    {
        'role': 'user',
        'content': 'Why is the sky blue?',
    },
    ])

    print(response.message.content)

def stockOutlook(stock_arr):
    # get stock outlook on webscraping
    # retrieve news about them from the database, if it exists, factor it into the final conclusion
    # provide account details for the LLM to give number of shares to buy/sell

    for ticker in stock_arr:

        file = open(f'backend/webscraping/tickerAnalysis/{ticker.lower()}.txt', 'r')
        contents = file.read()

        news_analysis = get_news_summary(ticker)


        messages = [
            {
                "role": "system",
                "content": """
        You are a financial research agent.
        You output ONLY valid JSON.
        No commentary, no markdown, no extra text.
        """
            },
            {
                "role": "user",
                "content": f"""
        Analyze the following news and holdings that appear in the news articles.

        Desired Approach: 

        We follow a long-term, conservative investment strategy centered on large, established (primarily Fortune 500) companies. The core portfolio closely tracks the S&P 500, but we actively monitor market trends and current events to identify opportunities for modest outperformance.
        When credible signals/news emerge, make small, targeted allocation adjustments toward companies or sectors expected to benefit. These adjustments are intentionally limited in size to manage risk, but are designed to compound over time.
        The goal is to outperform the S&P 500 through consistent, informed, incremental changes, rather than through speculative or high-risk investments such as penny stocks.
        
        Account details:
        
        Schema:
        - symbol: string
        - sentiment: number between -1 and 1
        - event_type: string
        - event_magnitude: low | medium | high
        - time_horizon: short_term | medium_term | long_term
        - uncertainty: number between 0 and 1
        - reason: max 25 words
        - held_stock: boolean
        - desired_quantity_shares: number


        News:
        {contents}
        {news_analysis}

        Output JSON with the above scheme only.
        """
            }
        ]

        response = chat(model="deepseek-r1:7b", messages=messages)

        raw = response.message.content

        if raw.startswith("```"):
            raw = raw.strip("```").strip().strip('json').strip('\n')

        print(raw)

        try:
            data = json.loads(raw)
            # saving analysis to database
            if data.sentiment > 1 or data.sentiment < 1:
                print("invalid json retrned by llm")
                return
            update_stock_analysis(ticker, data.sentiment, data.time_horizon, data.uncertainty, data.reason, data.desired_quantity_shares )
            return data
        except json.JSONDecodeError:
            print("Invalid JSON:", raw)


def summarizeMarketNews():
    # will summarize and organize market trends so that analysis can be done in each stock with this information
    # will deposit this in a new table in the database
    # then a decision can be made on whether to buy

    # feed in all current events to LLM - embed info so its easier to retrieve for the LLM

    file = open(f'backend/webscraping/todays_headlines.txt', 'r')
    contents = file.readlines()

    client = chromadb.Client()
    collection = client.create_collection(name='news')

    for i, article in enumerate(contents):
        sentences = # insert somethign else here
        chunks = chunk_sentences(sentences)

        for j, chunk in enumerate(chunks):
            response = ollama.embed(model="mxbai-embed-large", input=chunk)

            collection.add(ids=[f"{i}_{j}"], embeddings=response["embeddings"], documents=[chunk])

    query = "Summarize news by stock ticker"
    response = ollama.embed(model="mxbai-embed-large", input=query)


    results = collection.query(query_embeddings=response["embeddings"], n_results=1)

    
    context = " ".join(results["documents"][0]) if results["documents"] else ""


    messages = [
    {"role": "system", "content": "You are a financial research agent. Output ONLY a valid JSON array."},
    {"role": "user", "content": f"""
    Analyze/Summarize the following news for each stock that is mentioned in the articles: Use as much detail as possible for as many stocks as possible.

    JSON Schema:
    - symbol: ticker/symbol of the stock (not the full name of the company)
    - marketAnalysis: string

    Input:
    {context}

    Output JSON array ONLY.
    """}
    ]

    output = ollama.chat(model="deepseek-r1:7b", messages=messages)
    raw = output["message"]["content"]

    print(raw)

    raw = raw.strip()

    if raw.startswith("```"):
        raw = raw.strip("```").strip().strip('json').strip('\n')

    analysed_stock = []

    data = json.loads(raw)
    # saving analysis to database
    for stock in data:
        update_news_analysis(stock['symbol'], stock['marketAnalysis'] )
        analysed_stock.append(stock['symbol'])
    return analysed_stock
# ^deprecated code above




held_stock = ["AAPL", "NVDA", "MSFT", "AMZN"]
analysed_stock = summarizeMarketNews()
stockOutlook(held_stock)
analysisHeldStock(analysed_stock)
stockOutlook(analysed_stock)

print(test())
'''

## REAL CODE STARTS HERE
agent = create_agent(model, tools=[])
analysis_output = agent.invoke(
        {"messages": [{"role": "user", 
                       "content": f""" Hello world! tell me star wars joke!       """
        }]}
    )
print(analysis_output)





